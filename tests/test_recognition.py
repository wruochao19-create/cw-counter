import unittest
from recognition import Reader, Calibration
from fixtures import message_frame
from counter import CounterSession


class PixelTests(unittest.TestCase):
    def test_scaled_fonts_and_party_pipeline(self):
        for size in (10, 14, 20):
            with self.subTest(size=size):
                reader = Reader(size)
                session = CounterSession({'A': 123})
                reader.read(message_frame([], size), 0)
                lines = [('exp',123,'white',255), ('exp',123,'yellow',250),
                         ('bonus',12,'yellow',245)]
                for n in range(1, 5):
                    for event in reader.read(message_frame(lines, size), n * .1)[0]:
                        session.accept(**event)
                self.assertEqual(session.counts['A'], 1)
                self.assertEqual(session.party_exp, 135)
                self.assertEqual(session.personal_exp, 123)

    def test_template_reading_of_exp_bonus_and_mesos(self):
        reader = Reader(20)
        frame = message_frame([('exp',123,'white',255),('bonus',12,'yellow',240),('mesos',456,'white',220)])
        rows = reader.inspect(frame)
        parsed = [row[2][:2] for row in rows if row[2]]
        self.assertIn(('exp',123), parsed)
        self.assertIn(('bonus',12), parsed)
        self.assertIn(('mesos',456), parsed)

    def test_scroll_dedup_repeated_identical_exp(self):
        reader = Reader(20)
        output = []
        frames = [[], [('exp',123,'white',255)], [('exp',123,'white',250)],
                  [('exp',123,'white',245)],
                  [('exp',123,'white',255),('exp',123,'white',200)],
                  [('exp',123,'white',250),('exp',123,'white',195)],
                  [('exp',123,'white',245),('exp',123,'white',190)]]
        for i, lines in enumerate(frames):
            events, _ = reader.read(message_frame(lines), i * 0.1)
            output.extend(events)
        self.assertEqual([(e['kind'],e['amount']) for e in output], [('exp',123),('exp',123)])
        self.assertTrue(all(e['confident'] for e in output))

    def test_starting_messages_do_not_count_and_gap_resets(self):
        reader = Reader(20)
        frame = message_frame([('exp',123,'white',255)])
        self.assertEqual(reader.read(frame, 0)[0], [])
        self.assertEqual(reader.read(frame, 0.1)[0], [])
        events, gap = reader.read(frame, 2)
        self.assertTrue(gap)
        self.assertEqual(events, [])

    def test_region_follows_right_bottom_anchor(self):
        cal = Calibration(1920,1080,7,7,154.35)
        before = cal.box()
        cal.width += 100
        after = cal.box()
        self.assertEqual(after[0]-before[0],100)
        self.assertEqual(after[1],before[1])


if __name__ == '__main__':
    unittest.main()

