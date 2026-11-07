import csv
import tempfile
import unittest
from pathlib import Path
from counter import CounterSession, parse_monsters


class AccountingTests(unittest.TestCase):
    def test_repeated_exp_is_two_kills_but_same_event_is_once(self):
        s = CounterSession({'A': 123})
        for event in ('1', '2', '2'):
            s.accept(event, 'exp', 123, 'white')
        self.assertEqual(s.counts['A'], 2)
        self.assertEqual(s.personal_exp, 246)

    def test_party_and_bonus_never_count_as_kills(self):
        s = CounterSession({'A': 123})
        s.accept('1', 'exp', 123, 'yellow')
        s.accept('2', 'bonus', 123, 'white')
        self.assertEqual(sum(s.counts.values()), 0)
        self.assertEqual(s.party_exp, 246)

    def test_mixed_monsters_ambiguous_and_unknown(self):
        s = CounterSession({'A': 123, 'B': 456, 'C': 456})
        s.accept('1', 'exp', 123, 'white')
        s.accept('2', 'exp', 456, 'white')
        s.accept('3', 'exp', 789, 'white')
        self.assertEqual(dict(s.counts), {'A': 1})
        self.assertEqual(s.unresolved, 2)

    def test_uncertain_is_not_silently_promoted(self):
        s = CounterSession({'A': 123})
        s.accept('1', 'exp', 123, 'white', confident=False)
        self.assertEqual(sum(s.counts.values()), 0)
        self.assertEqual(s.unresolved, 1)

    def test_csv_is_saved_incrementally_and_formula_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = CounterSession({'=name': 123}, character='@char')
            s.open_log(tmp)
            s.accept('1', 'exp', 123, 'white')
            with s.path.open(encoding='utf-8-sig', newline='') as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[-1]['monster'], "'=name")
            s.export_summary(Path(tmp) / 'summary.csv')
            s.close()

    def test_profile_validation(self):
        self.assertEqual(parse_monsters('# comment\nA,123\nB,456'), {'A': 123, 'B': 456})
        for text in ('A,0', 'A,-2', 'A,no', 'A,1\nA,2'):
            with self.assertRaises(ValueError):
                parse_monsters(text)


if __name__ == '__main__':
    unittest.main()

