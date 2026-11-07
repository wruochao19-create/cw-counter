import unittest
from unittest.mock import patch
from PIL import Image
from pathlib import Path
from character_reader import CharacterMonitor,identify_character


class CharacterTests(unittest.TestCase):
    def test_name_from_the_users_actual_hud_crop(self):
        image=Image.open(Path(__file__).parent/'data/user-hud-name.png').convert('RGB')
        self.assertEqual(identify_character(image),'AncPenguin')

    def test_name_requires_two_consistent_startup_reads(self):
        names=iter(['AncPenguin','WrongName','AncPenguin'])
        monitor=CharacterMonitor(lambda image:next(names))
        self.assertIsNone(monitor.observe(None))
        self.assertIsNone(monitor.observe(None))
        self.assertIsNone(monitor.observe(None))
        self.assertTrue(monitor.done)
        monitor=CharacterMonitor(lambda image:'AncPenguin')
        self.assertIsNone(monitor.observe(None))
        self.assertEqual(monitor.observe(None),'AncPenguin')

    def test_name_must_be_next_to_a_job_label_not_chat_or_nearby_player(self):
        rows=[dict(text='Assassin',score=.99,box=(40,10,90,20)),
              dict(text='AncPenguin',score=.99,box=(40,21,100,31)),
              dict(text='SomeOtherPlayer',score=.99,box=(180,60,250,70))]
        with patch('character_reader.scan',return_value=rows):
            self.assertEqual(identify_character(Image.new('RGB',(300,100))),'AncPenguin')
        with patch('character_reader.scan',return_value=rows[1:]):
            self.assertIsNone(identify_character(Image.new('RGB',(300,100))))
