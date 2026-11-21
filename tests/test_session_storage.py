import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from session_storage import prune_sessions,active_logs
from counter import CounterSession


class StorageTests(unittest.TestCase):
    def test_keep_15_groups_by_start_time_preserving_unrelated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for n in range(20):
                for kind in ('events','summary'):
                    (root/f'20261121-120000-{n:06d}-{kind}.csv').write_text('data')
            unrelated=root/'my-export.csv';unrelated.write_text('keep')
            nested=root/'nested';nested.mkdir()
            (nested/'20261121-120000-000000-events.csv').write_text('keep')
            self.assertEqual(len(prune_sessions(root)),10)
            self.assertEqual(len(list(root.glob('*-events.csv'))),15)
            self.assertFalse((root/'20261121-120000-000004-summary.csv').exists())
            self.assertTrue((root/'20261121-120000-000005-summary.csv').exists())
            self.assertTrue(unrelated.exists())
            self.assertTrue(next(nested.iterdir()).exists())
            self.assertEqual(prune_sessions(root),[])

    def test_active_old_session_kept_with_14_newer_groups(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for n in range(18):
                (root/f'20261121-120000-{n:06d}-events.csv').write_text('data')
            old=(root/'20261121-120000-000000-events.csv').resolve()
            active_logs.add(old)
            try:
                prune_sessions(root)
                self.assertTrue(old.exists())
                self.assertEqual(len(list(root.iterdir())),15)
            finally:active_logs.discard(old)

    def test_locked_event_log_keeps_its_summary_and_does_not_raise(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            event=root/'20261121-120000-000000-events.csv'
            summary=root/'20261121-120000-000000-summary.csv'
            for p in (event,summary,root/'20261121-120000-000001-events.csv'):p.write_text('data')
            original=Path.unlink
            def unlink(path,*args,**kwargs):
                if path==event:raise PermissionError('open in another process')
                return original(path,*args,**kwargs)
            with patch.object(Path,'unlink',unlink):self.assertEqual(prune_sessions(root,limit=1),[])
            self.assertTrue(summary.exists())

    def test_real_counter_lifecycle_prunes_without_losing_latest_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for n in range(17):
                (root/f'20000101-120000-{n:06d}-events.csv').write_text('old')
            s=CounterSession();s.open_log(root)
            self.assertEqual(len(list(root.glob('*-events.csv'))),15)
            self.assertIn(s.path.resolve(),active_logs)
            summary=s.path.with_name(s.path.name.replace('-events','-summary'))
            s.export_summary(summary);s.close()
            self.assertNotIn(s.path.resolve(),active_logs)
            self.assertTrue(summary.exists())
            self.assertEqual(len(list(root.glob('*-events.csv'))),15)
