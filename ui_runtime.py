"""Load the small UI library and its process-private antialiased shape font."""
import contextlib
import ctypes
import io
from pathlib import Path
import sys

# Restricted Windows environments may reject font paths even when the file is
# readable. Memory fonts belong only to this process and disappear on exit.
messages = io.StringIO()
with contextlib.redirect_stderr(messages):
    import customtkinter as ctk

if sys.platform == 'win32' and ctk.DrawEngine.preferred_drawing_method == 'circle_shapes':
    try:
        data = (Path(ctk.__file__).parent/'assets/fonts/CustomTkinter_shapes_font.otf').read_bytes()
        buffer = ctypes.create_string_buffer(data)
        count = ctypes.c_uint()
        gdi = ctypes.WinDLL('gdi32')
        gdi.AddFontMemResourceEx.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
        gdi.AddFontMemResourceEx.restype = ctypes.c_void_p
        _font_handle = gdi.AddFontMemResourceEx(buffer, len(data), None, ctypes.byref(count))
        if _font_handle:
            ctk.DrawEngine.preferred_drawing_method = 'font_shapes'
    except (OSError, AttributeError):
        pass  # CTk's circle renderer remains a functional fallback.
warning = messages.getvalue()
if ctk.DrawEngine.preferred_drawing_method == 'font_shapes':
    warning = warning.replace("customtkinter.windows.widgets.font warning: Preferred drawing method 'font_shapes' can not be used because the font file could not be loaded.\nUsing 'circle_shapes' instead. The rendering quality will be bad!\n", '')
if warning:
    sys.stderr.write(warning)


def cleanup_callbacks(root):
    """Cancel this Tk interpreter's timers before its widget commands disappear."""
    for timer in root.tk.call('after', 'info'):
        root.after_cancel(timer)
    for window in list(ctk.ScalingTracker.window_widgets_dict):
        if window.tk is root.tk:
            ctk.ScalingTracker.window_widgets_dict.pop(window, None)
            ctk.ScalingTracker.window_dpi_scaling_dict.pop(window, None)
    ctk.AppearanceModeTracker.app_list[:] = [app for app in ctk.AppearanceModeTracker.app_list if app.tk is not root.tk]
    # The app uses one Tk root; tests may construct the next instance in-process.
    ctk.AppearanceModeTracker.update_loop_running = False
    ctk.ScalingTracker.update_loop_running = False
