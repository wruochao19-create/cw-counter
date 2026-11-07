import ctypes
import unittest
from unittest.mock import patch
import windows_capture as capture


class OverlayTests(unittest.TestCase):
    def check(self, rectangle, above=True, visible=True):
        def bounds(hwnd, output):
            rect=ctypes.cast(output,ctypes.POINTER(capture.w.RECT)).contents
            rect.left,rect.top,rect.right,rect.bottom=rectangle
            return True
        with patch.object(capture,'_overlay_windows',frozenset({22})), \
             patch.object(capture.user32,'IsWindowVisible',return_value=visible), \
             patch.object(capture.user32,'IsIconic',return_value=False), \
             patch.object(capture.user32,'GetWindowRect',side_effect=bounds), \
             patch.object(capture.user32,'GetWindow',side_effect=lambda h,flag:22 if above and h==11 else 0):
            return capture.overlay_occludes(11,(100,100,1000,800),(800,600,1000,700))

    def test_native_frame_overlap_relative_coordinates_and_z_order(self):
        self.assertTrue(self.check((950,720,1200,850)))
        self.assertFalse(self.check((950,720,1200,850),above=False))
        self.assertFalse(self.check((950,720,1200,850),visible=False))
        self.assertFalse(self.check((100,200,400,500)))
        self.assertFalse(self.check((1100,700,1200,900)))  # Touching edge only.

    def test_occluded_screen_never_reaches_ocr(self):
        with patch.object(capture,'client_rect',return_value=(0,0,1000,800)), \
             patch.object(capture,'overlay_occludes',return_value=True), \
             patch('PIL.ImageGrab.grab') as grab:
            with self.assertRaisesRegex(RuntimeError,'移开'):
                capture.grab_region(11,(0,0,100,100))
            grab.assert_not_called()

    def test_overlay_moving_over_region_during_capture_discards_image(self):
        with patch.object(capture,'client_rect',return_value=(0,0,1000,800)), \
             patch.object(capture,'overlay_occludes',side_effect=[False,True]), \
             patch('PIL.ImageGrab.grab') as grab:
            with self.assertRaisesRegex(RuntimeError,'移开'):
                capture.grab_region(11,(0,0,100,100))
            grab.assert_called_once()
