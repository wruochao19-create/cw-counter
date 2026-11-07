"""Visible desktop pixels + window geometry. No process handles/memory/input/network."""
import ctypes
from ctypes import wintypes as w
import sys

if sys.platform != 'win32':
    raise RuntimeError('实时捕获仅支持 Windows；离线识别不需要此模块。')

user32 = ctypes.WinDLL('user32', use_last_error=True)
user32.GetClientRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
user32.GetClientRect.restype = w.BOOL
user32.ClientToScreen.argtypes = [w.HWND, ctypes.POINTER(w.POINT)]
user32.ClientToScreen.restype = w.BOOL
user32.GetWindowTextLengthW.argtypes = [w.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [w.HWND]
user32.IsWindow.argtypes = [w.HWND]
user32.IsIconic.argtypes = [w.HWND]
user32.GetForegroundWindow.restype = w.HWND
CALLBACK = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
user32.EnumWindows.argtypes = [CALLBACK, w.LPARAM]
user32.GetSystemMetrics.argtypes=[ctypes.c_int]
user32.GetSystemMetrics.restype=ctypes.c_int
user32.GetAncestor.argtypes = [w.HWND, w.UINT]
user32.GetAncestor.restype = w.HWND
user32.GetWindow.argtypes = [w.HWND, w.UINT]
user32.GetWindow.restype = w.HWND
user32.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
user32.GetWindowRect.restype = w.BOOL
_overlay_windows = frozenset()


def root_window(hwnd):
    return int(user32.GetAncestor(hwnd, 2) or hwnd)


def register_overlay(hwnd):
    global _overlay_windows
    _overlay_windows = _overlay_windows | {hwnd}


def unregister_overlay(hwnd):
    global _overlay_windows
    _overlay_windows = _overlay_windows - {hwnd}


def rectangles_overlap(a, b):
    return max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3])


def overlay_occludes(hwnd, rect, box):
    return bool(overlay_regions(hwnd, rect, box))


def overlay_regions(hwnd, rect, box):
    """Check our visible windows only, including frame, in native Z order.

    Immutable handle snapshots are safe for the HUD worker. No Tk calls here.
    Ordinary non-topmost windows behind CW do not block capture.
    """
    x, y, _, _ = rect
    absolute = (x+box[0], y+box[1], x+box[2], y+box[3])
    overlaps = {}
    for handle in _overlay_windows:
        if handle == hwnd or not user32.IsWindowVisible(handle) or user32.IsIconic(handle):
            continue
        bounds = w.RECT()
        if user32.GetWindowRect(handle, ctypes.byref(bounds)):
            if rectangles_overlap(absolute, (bounds.left, bounds.top, bounds.right, bounds.bottom)):
                overlaps[handle]=(max(absolute[0],bounds.left)-absolute[0],
                                  max(absolute[1],bounds.top)-absolute[1],
                                  min(absolute[2],bounds.right)-absolute[0],
                                  min(absolute[3],bounds.bottom)-absolute[1])
    if not overlaps:
        return ()
    seen = set()
    blocked=[]
    above = user32.GetWindow(hwnd, 3)  # GW_HWNDPREV: next window above CW.
    while above and above not in seen and len(seen) < 512:
        if above in overlaps:
            blocked.append(overlaps[above])
        seen.add(above)
        above = user32.GetWindow(above, 3)
    return tuple(sorted(overlaps.values() if above else blocked))


def enable_dpi():
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        user32.SetProcessDPIAware()


def client_rect(hwnd):
    if not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
        return None
    rect, origin = w.RECT(), w.POINT(0, 0)
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)) or not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        return None
    if rect.right <= 0 or rect.bottom <= 0:
        return None
    return origin.x, origin.y, rect.right, rect.bottom


def enumerate_windows():
    result = []
    @CALLBACK
    def collect(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            rect = client_rect(hwnd)
            if title.value and rect and rect[2] >= 300 and rect[3] >= 200:
                result.append((int(hwnd), title.value))
        return True
    user32.EnumWindows(collect, 0)
    return sorted(result, key=lambda item: ('maple' not in item[1].lower(), item[1].lower()))


def foreground(hwnd):
    return user32.GetForegroundWindow() == hwnd


def window_exists(hwnd):
    return bool(hwnd and user32.IsWindow(hwnd))


def monitor_rectangles():
    rectangles=[]
    callback_type=ctypes.WINFUNCTYPE(w.BOOL,w.HMONITOR,w.HDC,ctypes.POINTER(w.RECT),w.LPARAM)
    @callback_type
    def collect(monitor,dc,rect,data):
        r=rect.contents
        rectangles.append((r.left,r.top,r.right,r.bottom))
        return True
    user32.EnumDisplayMonitors.argtypes=[w.HDC,ctypes.c_void_p,callback_type,w.LPARAM]
    user32.EnumDisplayMonitors(None,None,collect,0)
    return rectangles


def covered_by_monitors(box,monitors):
    """Rectangle subtraction also handles gaps between multiple displays."""
    remaining=[box]
    for ml,mt,mr,mb in monitors:
        next_remaining=[]
        for l,t,r,b in remaining:
            il,it,ir,ib=max(l,ml),max(t,mt),min(r,mr),min(b,mb)
            if il>=ir or it>=ib:
                next_remaining.append((l,t,r,b));continue
            next_remaining.extend(region for region in ((l,t,r,it),(l,ib,r,b),(l,it,il,ib),(ir,it,r,ib))
                                  if region[0]<region[2] and region[1]<region[3])
        remaining=next_remaining
    return not remaining


def region_on_screen(rect,box):
    x,y,width,height=rect
    l,t,r,b=box
    return covered_by_monitors((x+l,y+t,x+r,y+b),monitor_rectangles())


def visible_region(rect,box,monitors=None):
    x,y,width,height=rect
    l,t,r,b=box
    monitors=monitor_rectangles() if monitors is None else monitors
    absolute=(x+l,y+t,x+r,y+b)
    if covered_by_monitors(absolute,monitors):
        return tuple(box)
    intersections=[]
    for ml,mt,mr,mb in monitors:
        il,it,ir,ib=max(x+l,ml),max(y+t,mt),min(x+r,mr),min(y+b,mb)
        if il<ir and it<ib:
            intersections.append((il-x,it-y,ir-x,ib-y))
    return max(intersections,key=lambda area:(area[2]-area[0])*(area[3]-area[1]),default=None)


def grab_region(hwnd, relative_box, *, mask_overlay=False):
    from PIL import ImageGrab
    rect = client_rect(hwnd)
    if rect is None:
        raise RuntimeError('窗口关闭或最小化')
    x, y, width, height = rect
    left, top, right, bottom = relative_box
    if left < 0 or top < 0 or right > width or bottom > height:
        raise RuntimeError('提示区域超出游戏画面，请重新校准')
    masks=overlay_regions(hwnd,rect,relative_box) if mask_overlay else ()
    if not mask_overlay and overlay_occludes(hwnd, rect, relative_box):
        raise RuntimeError('统计面板遮住识别区域，请将面板移开')
    image = ImageGrab.grab(bbox=(x + left, y + top, x + right, y + bottom), all_screens=True)
    if not mask_overlay and overlay_occludes(hwnd, rect, relative_box):
        raise RuntimeError('统计面板遮住识别区域，请将面板移开')
    if mask_overlay:
        from PIL import ImageDraw
        masks=tuple(sorted(set(masks+overlay_regions(hwnd,rect,relative_box))))
        draw=ImageDraw.Draw(image)
        for l,t,r,b in masks:draw.rectangle((l,t,r-1,b-1),fill='black')
        image.info['overlay_masks']=masks
    return image

