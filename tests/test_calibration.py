import unittest
import tkinter as tk
from types import SimpleNamespace
from PIL import Image
from recognition import Calibration, Reader, fit_image, locate_text
from fixtures import message_frame
from calibration_ui import CalibrationDialog,move_box,suggested_box


class RegionTests(unittest.TestCase):
    def test_suggested_box_contains_known_notification_and_move_clamps(self):
        l,t,r,b=suggested_box(2560,1600)
        self.assertTrue(l<2285<r and t<1275<b)
        self.assertEqual(move_box((100,100,400,300),900,900,1000,700),(700,500,1000,700))
    def test_fit_preserves_all_four_corners_with_letterboxing(self):
        scale,x,y = fit_image(4000,2000,900,600)
        self.assertEqual((scale,x,y),(.225,0,75))
        self.assertEqual((4000*scale+x,2000*scale+y),(900,525))

    def test_reverse_drag_clamps_and_keeps_exact_region(self):
        cal=Calibration(1920,1080)
        cal.select((2000,900),(1200,600))
        self.assertEqual(cal.box(),(1200,600,1920,900))
        with self.assertRaises(ValueError):
            cal.select((1,1),(2,2))
        self.assertEqual(cal.box(),(1200,600,1920,900))

    def test_manual_region_flows_into_real_reader(self):
        frame=message_frame([('exp',123,'white',255)],20)
        # User includes extra padding; locate the text independently of that padding.
        padded=Image.new('RGB',(frame.width+40,frame.height+50))
        padded.paste(frame,(15,20))
        found=locate_text(padded,20)
        self.assertIsNotNone(found)
        cal=Calibration(1600,1000,20)
        cal.select((100,100),(100+padded.width,100+padded.height))
        cal.text_bottom,cal.text_right=found
        rows=Reader(20).inspect(cal.prepare(padded))
        self.assertIn(('exp',123),[r[2][:2] for r in rows if r[2]])

    def test_legacy_calibration_is_unchanged(self):
        image=Image.new('RGB',(400,160))
        self.assertIs(Calibration(1920,1080).prepare(image),image)


class DialogTests(unittest.TestCase):
    def test_drag_on_full_preview_and_single_click_does_not_move(self):
        root=tk.Tk()
        root.withdraw()
        original=Calibration(4000,2200)
        dialog=CalibrationDialog(root,Image.new('RGB',(4000,2200)),original,lambda c: None)
        dialog.window.withdraw()
        dialog.auto_align=lambda: None
        try:
            dialog.resize_preview(SimpleNamespace(width=1000,height=600))
            self.assertEqual(dialog.photo.width(),1000)
            self.assertEqual(dialog.photo.height(),550)
            self.assertEqual(dialog.image_point(0,25),(0,0))
            self.assertEqual(dialog.image_point(1000,575),(4000,2200))
            event=lambda x,y: SimpleNamespace(x=x,y=y)
            dialog.begin_drag(event(950,500))
            dialog.move_drag(event(700,400))
            dialog.end_drag(event(700,400))
            self.assertEqual(dialog.cal.box(),(2800,1500,3800,1900))
            self.assertIsNone(original.region)  # Cancel must not alter the app's calibration.
            previous=dialog.cal.box()
            for _ in range(2):
                dialog.begin_drag(event(200,200))
                dialog.end_drag(event(200,200))
            self.assertEqual(dialog.cal.box(),previous)
            # Resize the full preview: the saved source-pixel region is unchanged.
            dialog.resize_preview(SimpleNamespace(width=800,height=500))
            self.assertEqual(dialog.cal.box(),previous)
            root.update_idletasks()
        finally:
            dialog.window.destroy()
            root.destroy()

    def test_saved_region_is_reused_and_can_be_moved_and_resized(self):
        root=tk.Tk();root.withdraw()
        cal=Calibration(1000,600,region=[700,350,950,500])
        dialog=CalibrationDialog(root,Image.new('RGB',(1000,600)),cal,lambda c:None)
        dialog.window.withdraw()
        try:
            dialog.resize_preview(SimpleNamespace(width=1000,height=600))
            self.assertEqual(dialog.cal.box(),(700,350,950,500))
            event=lambda x,y:SimpleNamespace(x=x,y=y)
            dialog.begin_drag(event(800,400));dialog.end_drag(event(750,380))
            self.assertEqual(dialog.cal.box(),(650,330,900,480))
            dialog.begin_drag(event(900,480));dialog.end_drag(event(970,550))
            self.assertEqual(dialog.cal.box(),(650,330,970,550))
            self.assertEqual(cal.box(),(700,350,950,500))
        finally:dialog.window.destroy();root.destroy()


if __name__ == '__main__':
    unittest.main()
