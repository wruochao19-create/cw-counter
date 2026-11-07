import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch
from counter import CounterSession
import app
from sidebar_ui import apply_topmost, open_settings, close_settings
from modern_sidebar import apply_appearance, apply_opacity, reset_appearance, apply_layout, toggle_mini, BACK


class LayoutTests(unittest.TestCase):
    def test_mini_and_sections_preserve_live_session_and_restore_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'settings.json'
            with patch.object(app,'CONFIG',path),patch.object(app.capture,'enumerate_windows',return_value=[]):
                root=tk.Tk();ui=app.App(root)
                try:
                    ui.session=CounterSession({'Wild Boar':46});session=ui.session
                    session.counts['Wild Boar']=8;ui.update_stats()
                    root.update();root.after(50);root.update()
                    full_height=root.winfo_height()
                    ui.visible_sections['eta'].set(False);apply_layout(ui,persist=True)
                    self.assertFalse(ui.section_widgets['eta'][0].winfo_manager())
                    toggle_mini(ui);root.update();root.after(50);root.update()
                    self.assertLess(root.winfo_height(),full_height-100)
                    self.assertFalse(ui.list_frame.winfo_manager())
                    self.assertTrue(ui.hero_value.winfo_manager())
                    self.assertTrue(ui.start_button.winfo_manager())
                    session.counts['Wild Boar']=12;ui.update_stats()
                    self.assertEqual(ui.table.item('Wild Boar','values')[1],'12')
                    toggle_mini(ui);root.update();root.after(50);root.update()
                    self.assertIs(ui.session,session)
                    self.assertTrue(ui.list_frame.winfo_manager())
                    self.assertFalse(ui.section_widgets['eta'][0].winfo_manager())
                    self.assertGreaterEqual(root.winfo_height(),full_height)
                    toggle_mini(ui)
                finally:ui.close()
                root=tk.Tk();ui=app.App(root)
                try:
                    self.assertTrue(ui.mini_mode.get())
                    self.assertFalse(ui.visible_sections['eta'].get())
                    self.assertFalse(ui.list_frame.winfo_manager())
                    toggle_mini(ui)
                    ui.visible_sections['monsters'].set(False)
                    apply_layout(ui,persist=True)
                    self.assertFalse(ui.list_frame.winfo_manager())
                    self.assertTrue(ui.section_widgets['progress'][0].winfo_manager())
                finally:ui.close()

    def test_theme_accent_and_opacity_apply_and_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'settings.json'
            with patch.object(app,'CONFIG',path),patch.object(app.capture,'enumerate_windows',return_value=[]):
                root=tk.Tk();ui=app.App(root)
                try:
                    ui.appearance.set('深色');ui.accent_name.set('松绿');ui.opacity.set(85)
                    apply_appearance(ui,persist=True);root.update()
                    self.assertEqual(root.cget('background'),BACK[1])
                    self.assertEqual(ui.start_button.cget('fg_color'),'#327b70')
                    self.assertAlmostEqual(root.attributes('-alpha'),.85,places=2)
                    self.assertAlmostEqual(ui.settings_window.attributes('-alpha'),1,places=2)
                    saved=json.loads(path.read_text('utf-8'))
                    self.assertEqual((saved['appearance'],saved['accent'],saved['opacity']),('深色','松绿',85))
                    self.assertTrue(ui.empty_label.winfo_manager())
                    ui.session.counts['Test mob']=1;ui.update_stats()
                    self.assertFalse(ui.empty_label.winfo_manager())
                    reset_appearance(ui);root.update()
                    self.assertEqual(root.cget('background'),BACK[0])
                    self.assertAlmostEqual(root.attributes('-alpha'),1,places=2)
                finally:ui.close()

    def test_long_monster_list_scroll_and_selection_survive_stat_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            with patch.object(app,'CONFIG',path/'settings.json'),patch.object(app.capture,'enumerate_windows',return_value=[]):
                root=tk.Tk();root.withdraw();ui=app.App(root)
                try:
                    self.assertEqual(len(ui.tabs.tabs()),5)
                    ui.session=CounterSession({f'Monster {i}':i+1 for i in range(40)})
                    ui.update_stats()
                    self.assertEqual(len(ui.table.get_children()),0)
                    for name in ui.session.monsters:ui.session.counts[name]=1
                    ui.update_stats()
                    self.assertEqual(len(ui.table.get_children()),40)
                    ui.table.selection_set('Monster 35')
                    ui.update_stats()
                    self.assertEqual(ui.table.selection(),('Monster 35',))
                    self.assertGreaterEqual(int(ui.table.cget('height')),8)
                    self.assertTrue(ui.table.cget('yscrollcommand'))
                    self.assertTrue(ui.monsters.cget('yscrollcommand'))
                    self.assertIn('开始后',ui.character_hint.get())
                finally:ui.close()

    def test_sidebar_resizes_scrolls_and_remembers_topmost(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'settings.json'
            with patch.object(app,'CONFIG',path),patch.object(app.capture,'enumerate_windows',return_value=[]):
                root=tk.Tk();ui=app.App(root)
                try:
                    self.assertEqual(tuple(map(bool,root.resizable())),(True,True))
                    self.assertEqual(ui.settings_window.state(),'withdrawn')
                    ui.session=CounterSession({f'Monster {i}':i+1 for i in range(60)})
                    for name in ui.session.monsters:ui.session.counts[name]=1
                    ui.update_stats()
                    minimum=root.minsize()
                    root.geometry(f'{minimum[0]}x{minimum[1]}');root.update();root.after(50);root.update()
                    small=ui.table.winfo_height()
                    self.assertGreater(small,60,'List must remain usable at minimum size')
                    self.assertLessEqual(ui.start_button.winfo_rooty()+ui.start_button.winfo_height(),root.winfo_rooty()+root.winfo_height())
                    root.geometry(f'{minimum[0]+180}x{minimum[1]+250}');root.update();root.after(50);root.update()
                    self.assertGreater(ui.table.winfo_height(),small+150)
                    ui.table.yview_moveto(1);root.update()
                    position=ui.table.yview()
                    self.assertGreater(position[0],0)
                    ui.table.selection_set('Monster 59');ui.update_stats();root.update()
                    self.assertEqual(ui.table.selection(),('Monster 59',))
                    self.assertAlmostEqual(ui.table.yview()[0],position[0],places=2)
                    ui.topmost.set(False);apply_topmost(ui,persist=True);root.update()
                    self.assertFalse(root.attributes('-topmost'))
                    self.assertFalse(json.loads(path.read_text('utf-8'))['always_on_top'])
                    ui.topmost.set(True);apply_topmost(ui);root.update()
                    self.assertTrue(root.attributes('-topmost'))
                    open_settings(ui);root.update()
                    self.assertEqual(ui.settings_window.state(),'normal')
                    close_settings(ui)
                    self.assertEqual(ui.settings_window.state(),'withdrawn')
                finally:ui.close()
