import threading
import time
import unittest

from async_reader import AsyncNotificationReader


class FakeReader:
    def __init__(self):
        self.profile = {'Old': 35}
        self.last_lines = []
        self.last_diagnostics = {}
        self.entered = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()
        self.operations = []
        self.thread_ids = []
        self.reads = 0

    def note(self, operation):
        self.operations.append(operation)
        self.thread_ids.append(threading.get_ident())

    def read(self, image, timestamp):
        self.note(('read', image, timestamp, dict(self.profile)))
        self.reads += 1
        self.entered.set()
        if not self.release.wait(2):
            raise RuntimeError('Test did not release fake OCR')
        self.last_lines = [{'image': image, 'value': self.reads}]
        self.last_diagnostics = {'read': self.reads}
        self.finished.set()
        return [{'image': image, 'number': self.reads}], False

    def reset(self):
        self.note(('reset',))
        self.last_lines = []

    def set_profile(self, profile):
        self.note(('profile', dict(profile)))
        self.profile = dict(profile)

    def rebase(self, old_box, new_box):
        self.note(('rebase', old_box, new_box))

    def finish(self):
        self.note(('finish',))
        return [{'tail': True}]


class AsyncReaderTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeReader()
        self.reader = AsyncNotificationReader(self.fake)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.fake.release.set()
        self.reader.close()

    def wait_pending(self):
        self.reader._pending.result(timeout=2)

    def test_read_is_nonblocking_and_does_not_queue_images(self):
        started = time.monotonic()
        self.assertIsNone(self.reader.read('first', 1))
        self.assertTrue(self.fake.entered.wait(1))
        for n in range(50):
            self.assertIsNone(self.reader.read(f'dropped-{n}', n+2))
        self.assertLess(time.monotonic()-started, .5)
        self.assertEqual(self.fake.reads, 1)
        self.assertTrue(self.reader.busy)
        self.fake.release.set(); self.wait_pending()
        self.assertFalse(self.reader.busy)
        events, gap = self.reader.read('not-submitted', 80)
        self.assertEqual(events, [{'image': 'first', 'number': 1}])
        self.assertFalse(gap)
        self.assertEqual(self.reader.last_image, 'first')
        self.assertEqual(self.reader.last_timestamp, 1)
        self.assertEqual(self.reader.last_lines, [{'image': 'first', 'value': 1}])
        self.assertEqual(self.reader.last_diagnostics['read'], 1)
        self.assertIsNone(self.reader._pending)
        self.assertIsNone(self.reader.read('next', 81))
        self.wait_pending()
        self.assertEqual(self.fake.operations[-1][1], 'next')
        self.assertEqual(self.reader.last_lines, [{'image': 'first', 'value': 1}])

    def test_controls_are_ordered_and_old_generation_is_discarded(self):
        self.reader.read('obsolete', 1)
        self.assertTrue(self.fake.entered.wait(1))
        started = time.monotonic()
        self.reader.reset()
        self.reader.set_profile({'New': 58})
        self.reader.rebase((0, 1, 20, 30), (0, 2, 20, 30))
        self.assertLess(time.monotonic()-started, .2)
        self.assertEqual(self.reader.profile, {'New': 58})
        self.fake.release.set(); self.wait_pending()
        self.assertIsNone(self.reader.read('discarded', 2))
        self.assertIsNone(self.reader.read('new', 2.1))
        self.wait_pending()
        events, _ = self.reader.read('newer', 3)
        self.assertEqual(events[0]['image'], 'new')
        self.assertEqual([x[0] for x in self.fake.operations[:5]], ['read', 'reset', 'profile', 'rebase', 'read'])
        self.assertEqual(self.fake.operations[4][3], {'New': 58})
        self.assertEqual(len(set(self.fake.thread_ids)), 1)
        self.assertNotEqual(self.fake.thread_ids[0], threading.get_ident())

    def test_valid_is_checked_before_and_after_ocr(self):
        checks = iter([True, False])
        self.fake.release.set()
        self.reader.read('invalid-after', 1, valid=lambda: next(checks))
        self.wait_pending()
        self.assertIsNone(self.reader.read('not-submitted', 2))
        self.assertIsNone(self.reader.read('invalid-before', 2.1, valid=lambda: False))
        self.wait_pending()
        self.assertEqual(self.fake.reads, 1)
        self.assertEqual([op[0] for op in self.fake.operations], ['read', 'reset', 'reset'])
        self.assertEqual(self.reader.finish(), [{'tail': True}])
        self.assertIsNone(self.reader.last_image)

    def test_finish_collects_pending_frame_and_tail_exactly_once(self):
        self.reader.read('pending', 1)
        self.assertTrue(self.fake.entered.wait(1))
        self.fake.release.set()
        result = self.reader.finish()
        self.assertEqual(result, [{'image': 'pending', 'number': 1}, {'tail': True}])
        self.assertEqual(self.reader.finish(), [])
        self.assertEqual([op[0] for op in self.fake.operations].count('finish'), 1)

    def test_finish_timeout_is_bounded_and_retry_does_not_repeat_tail(self):
        self.reader.read('slow', 1)
        self.assertTrue(self.fake.entered.wait(1))
        started = time.monotonic()
        self.assertEqual(self.reader.finish(timeout=.02), [])
        self.assertLess(time.monotonic()-started, .2)
        self.assertIsNone(self.reader.read('not-queued', 2))
        self.fake.release.set()
        self.assertEqual(self.reader.finish(), [{'image': 'slow', 'number': 1}, {'tail': True}])
        self.assertEqual(self.reader.finish(), [])
        self.assertEqual(self.fake.reads, 1)

    def test_reset_after_finish_timeout_discards_obsolete_settlement(self):
        self.reader.read('old', 1)
        self.assertTrue(self.fake.entered.wait(1))
        self.reader.finish(timeout=.01)
        self.reader.reset()
        self.fake.release.set()
        self.assertIsNone(self.reader.read('new', 2))
        self.wait_pending()
        self.assertEqual(self.reader.finish(), [{'image': 'new', 'number': 2}, {'tail': True}])
        self.assertEqual([op[0] for op in self.fake.operations].count('finish'), 1)

    def test_close_does_not_wait_or_accept_more_work(self):
        self.reader.read('running', 1)
        self.assertTrue(self.fake.entered.wait(1))
        self.reader.reset()
        started = time.monotonic(); self.reader.close()
        self.reader.close()  # Idempotent even while the old task is still running.
        self.assertLess(time.monotonic()-started, .2)
        self.assertIsNone(self.reader.read('no', 2))
        self.assertEqual(self.reader.finish(), [])
        self.fake.release.set()
        self.assertTrue(self.fake.finished.wait(1))
        self.assertEqual([op[0] for op in self.fake.operations], ['read'])


if __name__ == '__main__':
    unittest.main()
