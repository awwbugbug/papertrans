from __future__ import annotations

import ctypes
import os
from collections.abc import Callable
from typing import Any, Protocol


class NativeWindowApi(Protocol):
    def enable_resizable_frame(self, handle: int) -> None: ...

    def begin_move(self, handle: int) -> None: ...

    def begin_resize(self, handle: int, hit_test: int) -> None: ...

    def set_maximized(self, handle: int, maximized: bool) -> None: ...


_RESIZE_HIT_TESTS = {
    "west": 10,
    "east": 11,
    "north": 12,
    "northwest": 13,
    "northeast": 14,
    "south": 15,
    "southwest": 16,
    "southeast": 17,
}


class DesktopWindowFrame:
    """Restores native Windows move/resize behavior to a frameless pywebview window."""

    def __init__(
        self,
        *,
        native_api: NativeWindowApi | None = None,
        ui_dispatch: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        self._native_api = native_api or (_Win32NativeApi() if os.name == "nt" else None)
        self._ui_dispatch = ui_dispatch
        self._window: Any | None = None

    def attach(self, window: Any) -> None:
        self._window = window

    def initialize(self) -> bool:
        handle = self._handle()
        if handle is None or self._native_api is None:
            return False

        def initialize_frame() -> None:
            self._native_api.enable_resizable_frame(handle)
            self._native_api.set_maximized(handle, False)

        self._dispatch(initialize_frame)
        return True

    def begin_move(self) -> bool:
        handle = self._handle()
        if handle is None or self._native_api is None:
            return False
        self._dispatch(lambda: self._native_api.begin_move(handle))
        return True

    def begin_resize(self, edge: str) -> bool:
        handle = self._handle()
        hit_test = _RESIZE_HIT_TESTS.get(edge)
        if handle is None or hit_test is None or self._native_api is None:
            return False
        self._dispatch(lambda: self._native_api.begin_resize(handle, hit_test))
        return True

    def set_maximized(self, maximized: bool) -> bool:
        handle = self._handle()
        if handle is None or self._native_api is None:
            return False
        self._dispatch(lambda: self._native_api.set_maximized(handle, maximized))
        return True

    def _handle(self) -> int | None:
        native = getattr(self._window, "native", None)
        value = getattr(native, "Handle", None)
        if value is None:
            return None
        if hasattr(value, "ToInt64"):
            return int(value.ToInt64())
        return int(value)

    def _dispatch(self, callback: Callable[[], None]) -> None:
        if self._ui_dispatch is not None:
            self._ui_dispatch(callback)
            return
        native = getattr(self._window, "native", None)
        if native is None:
            callback()
            return
        try:
            from System import Action

            native.BeginInvoke(Action(callback))
        except (AttributeError, ImportError, TypeError):
            callback()


class _Win32NativeApi:
    _GWL_STYLE = -16
    _WS_THICKFRAME = 0x00040000
    _WS_MINIMIZEBOX = 0x00020000
    _WS_MAXIMIZEBOX = 0x00010000
    _WS_SYSMENU = 0x00080000
    _SWP_NOSIZE = 0x0001
    _SWP_NOMOVE = 0x0002
    _SWP_NOZORDER = 0x0004
    _SWP_NOACTIVATE = 0x0010
    _SWP_FRAMECHANGED = 0x0020
    _WM_NCLBUTTONDOWN = 0x00A1
    _HTCAPTION = 2
    _DWMWA_WINDOW_CORNER_PREFERENCE = 33
    _DWMWA_BORDER_COLOR = 34
    _DWMWA_COLOR_NONE = 0xFFFFFFFE
    _DWMWCP_DONOTROUND = 1
    _DWMWCP_ROUND = 2

    def __init__(self) -> None:
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
        self._get_style = self._user32.GetWindowLongPtrW
        self._get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._get_style.restype = ctypes.c_ssize_t
        self._set_style = self._user32.SetWindowLongPtrW
        self._set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
        self._set_style.restype = ctypes.c_ssize_t
        self._user32.SetWindowPos.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        self._user32.SetWindowPos.restype = ctypes.c_bool
        self._user32.ReleaseCapture.argtypes = []
        self._user32.ReleaseCapture.restype = ctypes.c_bool
        self._user32.SendMessageW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        ]
        self._user32.SendMessageW.restype = ctypes.c_ssize_t
        self._dwmapi.DwmSetWindowAttribute.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_uint,
        ]
        self._dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long

    def enable_resizable_frame(self, handle: int) -> None:
        style = self._get_style(handle, self._GWL_STYLE)
        style &= ~self._WS_THICKFRAME
        style |= self._WS_MINIMIZEBOX | self._WS_MAXIMIZEBOX | self._WS_SYSMENU
        self._apply_style(handle, style)

    def _apply_style(self, handle: int, style: int) -> None:
        self._set_style(handle, self._GWL_STYLE, style)
        self._user32.SetWindowPos(
            handle,
            None,
            0,
            0,
            0,
            0,
            self._SWP_NOSIZE
            | self._SWP_NOMOVE
            | self._SWP_NOZORDER
            | self._SWP_NOACTIVATE
            | self._SWP_FRAMECHANGED,
        )

    def begin_move(self, handle: int) -> None:
        self._begin_with_temporary_resize_frame(handle, self._HTCAPTION)

    def begin_resize(self, handle: int, hit_test: int) -> None:
        self._begin_with_temporary_resize_frame(handle, hit_test)

    def _begin_with_temporary_resize_frame(self, handle: int, hit_test: int) -> None:
        original_style = self._get_style(handle, self._GWL_STYLE)
        if original_style & self._WS_THICKFRAME:
            self._begin_nonclient_action(handle, hit_test)
            return
        self._apply_style(handle, original_style | self._WS_THICKFRAME)
        try:
            self._begin_nonclient_action(handle, hit_test)
        finally:
            self._apply_style(handle, original_style)

    def set_maximized(self, handle: int, maximized: bool) -> None:
        style = self._get_style(handle, self._GWL_STYLE)
        if maximized:
            style |= self._WS_THICKFRAME
        else:
            style &= ~self._WS_THICKFRAME
        self._apply_style(handle, style)
        preference = ctypes.c_int(
            self._DWMWCP_DONOTROUND if maximized else self._DWMWCP_ROUND
        )
        self._dwmapi.DwmSetWindowAttribute(
            handle,
            self._DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(preference),
            ctypes.sizeof(preference),
        )
        border_color = ctypes.c_uint(self._DWMWA_COLOR_NONE)
        self._dwmapi.DwmSetWindowAttribute(
            handle,
            self._DWMWA_BORDER_COLOR,
            ctypes.byref(border_color),
            ctypes.sizeof(border_color),
        )

    def _begin_nonclient_action(self, handle: int, hit_test: int) -> None:
        self._user32.ReleaseCapture()
        self._user32.SendMessageW(handle, self._WM_NCLBUTTONDOWN, hit_test, 0)
