import unittest
from pixel_ocr import NotificationTracker
from tests.test_stress import line


def coin(value=100,y=300):
    row=line(value,y);row.update(said=('mesos',value),text=f'You have gained mesos (+{value})')
    return row


class InterleavedNotificationsTests(unittest.TestCase):
    def test_strong_digits_survive_a_weak_fixed_english_prefix(self):
        tracker=NotificationTracker();tracker.update([],0)
        row=line(35);row.update(score=.79,digit_min_score=.89)
        self.assertEqual(tracker.update([row],.3)[0],[])
        events=tracker.update([row],.6)[0]
        self.assertEqual(len(events),1);self.assertTrue(events[0]['confident'])

    def test_weak_prefix_without_strong_numeric_evidence_is_not_counted(self):
        tracker=NotificationTracker();tracker.update([],0)
        row=line(35);row.update(score=.79,digit_min_score=.72)
        events=[]
        for t in (.2,.4,.6,.8):events.extend(tracker.update([row],t)[0])
        events.extend(tracker.finish())
        self.assertEqual(len(events),1);self.assertFalse(events[0]['confident'])
    def test_deep_valley_exp_with_three_coin_messages_at_slow_sampling(self):
        expected=[21,32,43,46,60]*4
        schedule=[]
        for i,amount in enumerate(expected):
            birth=1+i*1.4;schedule.append((birth,'exp',amount))
            schedule.extend((birth+d,'mesos',100+i*3+j) for j,d in enumerate((.18,.45,.7)))
        schedule.sort()
        for sample in (.3,.75,1.):
            with self.subTest(sample=sample):
                tracker=NotificationTracker();events=[]
                for n in range(int(32/sample)):
                    now=n*sample
                    active=[r for r in reversed(schedule) if 0<=now-r[0]<4][:8]
                    rows=[]
                    for index,(born,kind,amount) in enumerate(active):
                        row=line(amount,300-index*24,255-(now-born)*30,230-(now-born)*30)
                        row['said']=(kind,amount);rows.append(row)
                    events.extend(tracker.update(rows,now)[0])
                self.assertEqual([e['amount'] for e in events if e['kind']=='exp' and e['confident']],expected)

    def test_new_exp_above_an_existing_coin_message_is_not_a_baseline(self):
        tracker=NotificationTracker();tracker.update([],0)
        for t in (.3,.6):tracker.update([coin()],t)
        events=[]
        for t in (.9,1.2):events.extend(tracker.update([coin(),line(21,275)],t)[0])
        self.assertEqual([e['amount'] for e in events if e['kind']=='exp'],[21])

    def test_multiple_new_exps_above_a_coin_are_not_discarded(self):
        tracker=NotificationTracker();tracker.update([],0)
        for t in (.3,.6):tracker.update([coin()],t)
        events=[]
        rows=[coin(),line(21,275),line(32,250),line(43,225)]
        for t in (.9,1.2):events.extend(tracker.update(rows,t)[0])
        self.assertEqual(sorted(e['amount'] for e in events if e['kind']=='exp'),[21,32,43])

    def test_one_second_ocr_dropout_keeps_a_completed_message_identity(self):
        tracker=NotificationTracker();tracker.update([],0)
        events=[]
        for t,rows in ((.2,[line(21)]),(.4,[line(21)]),(.7,[]),(1.1,[]),
                       (1.5,[line(21)]),(1.7,[line(21)])):
            events.extend(tracker.update(rows,t)[0])
        self.assertEqual(len(events),1)

    def test_one_frame_candidate_is_reported_uncertain_when_it_disappears(self):
        tracker=NotificationTracker();tracker.update([],0)
        tracker.update([line(21)],.2)
        events=[]
        for t in (.8,1.6,2.4,3.3):events.extend(tracker.update([],t)[0])
        self.assertEqual(len(events),1)
        self.assertFalse(events[0]['confident'])
        self.assertEqual(events[0]['amount'],21)
        self.assertEqual(tracker.finish(),[])

    def test_stop_exposes_pending_candidate_instead_of_silently_discarding_it(self):
        tracker=NotificationTracker();tracker.update([],0)
        tracker.update([line(21)],.2)
        self.assertEqual(len(tracker.finish()),1)
        self.assertEqual(tracker.finish(),[])
