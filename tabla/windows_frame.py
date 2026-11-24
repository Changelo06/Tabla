"""Windows Snap integration for Tabla's custom title bar."""
import sys
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication


def available():
    return sys.platform == 'win32' and QApplication.instance().platformName() == 'windows'


def apply_dwm(window, dark=None):
    """Apply Windows 11 DWM rounded corners, dark titlebar frame, and hairline border."""
    if not available():
        return
    try:
        import ctypes
        from ctypes import wintypes
        from .tokens import current_tokens
        t = current_tokens(dark)
        dwmapi = ctypes.windll.dwmapi
        hwnd = int(window.winId())
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        dark_val = ctypes.c_int(1 if t.dark else 0)
        dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), 20, ctypes.byref(dark_val), ctypes.sizeof(dark_val))
        # DWMWA_WINDOW_CORNER_PREFERENCE = 33 -> DWMWCP_ROUND = 2
        corner_pref = ctypes.c_int(2)
        dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), 33, ctypes.byref(corner_pref), ctypes.sizeof(corner_pref))
        # DWMWA_BORDER_COLOR = 34 (COLORREF is 0x00BBGGRR)
        border_bgr = ctypes.c_uint(0x002A2A2E if t.dark else 0x00E4E4E8)
        dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), 34, ctypes.byref(border_bgr), ctypes.sizeof(border_bgr))
    except Exception:
        pass


def configure(window):
    if not available():
        return
    import ctypes
    from ctypes import wintypes
    api = ctypes.windll.user32
    hwnd = int(window.winId())
    if getattr(window, '_snap_hwnd', None) == hwnd:
        apply_dwm(window)
        return
    window._snap_hwnd = hwnd
    api.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    api.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    api.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    style = api.GetWindowLongW(hwnd, -16)
    # Retain the native sizing/maximize capabilities that Windows Snap expects.
    api.SetWindowLongW(hwnd, -16, style | 0x00040000 | 0x00030000)
    api.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0037)
    apply_dwm(window)


def handle(window, message):
    if not available() or not hasattr(window, 'chrome'):
        return None
    import ctypes
    from ctypes import wintypes
    msg = wintypes.MSG.from_address(int(message))
    if msg.message == 0x0083 and msg.wParam:  # WM_NCCALCSIZE: preserve custom chrome.
        return True, 0
    if msg.message == 0x00A0:  # WM_NCMOUSEMOVE bypasses Qt's normal :hover state.
        hovered = msg.wParam == 9
        entering = hovered and not window.chrome.maximize.property('nativeHover')
        if hovered:
            window.chrome.set_native_maximize_hover(True)
        else:
            window.chrome.check_native_hover()
        if entering:
            class TrackMouse(ctypes.Structure):
                _fields_ = [('cbSize', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
                            ('hwndTrack', wintypes.HWND), ('dwHoverTime', wintypes.DWORD)]
            tracking = TrackMouse(ctypes.sizeof(TrackMouse), 0x12, msg.hWnd, 0)
            ctypes.windll.user32.TrackMouseEvent(ctypes.byref(tracking))
        # Let Windows handle Snap Layouts; only the visual hover belongs to Qt.
        return None
    if msg.message == 0x02A2:  # WM_NCMOUSELEAVE
        # The Snap flyout can take nonclient tracking without moving the cursor.
        window.chrome.check_native_hover()
    if msg.message in (0x00A1, 0x00A2) and msg.wParam == 9:
        window.chrome.maximize.setDown(msg.message == 0x00A1)
        if msg.message == 0x00A2:
            window.chrome.toggle_maximize()
        return True, 0
    if msg.message != 0x0084:  # WM_NCHITTEST
        return None
    point = wintypes.POINT(ctypes.c_short(msg.lParam & 0xffff).value,
                           ctypes.c_short((msg.lParam >> 16) & 0xffff).value)
    api = ctypes.windll.user32
    api.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    api.ScreenToClient(msg.hWnd, ctypes.byref(point))
    ratio = window.devicePixelRatioF()
    point = QPoint(round(point.x / ratio), round(point.y / ratio))
    maximize = window.chrome.maximize
    if maximize.rect().contains(maximize.mapFrom(window, point)):
        return True, 9  # HTMAXBUTTON enables the Windows 11 Snap Layout flyout.
    for control in (window.chrome.minimize, window.chrome.close_button):
        if control.rect().contains(control.mapFrom(window, point)):
            return True, 1  # The complete traffic-light slot is clickable.
    search = window.chrome.search
    if search.rect().contains(search.mapFrom(window, point)):
        return True, 1  # HTCLIENT: the title-bar search must accept typing, not drag.
    if not window.isMaximized():
        left, right = point.x() < 6, point.x() >= window.width() - 6
        top, bottom = point.y() < 6, point.y() >= window.height() - 6
        hit = 13 if top and left else 14 if top and right else 16 if bottom and left else 17 if bottom and right else 10 if left else 11 if right else 12 if top else 15 if bottom else 0
        if hit:
            return True, hit
    drag = window.chrome.drag_area
    if drag.rect().contains(drag.mapFrom(window, point)):
        return True, 2  # HTCAPTION: native dragging, double-click and edge snapping.
    return None
