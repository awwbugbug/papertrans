from types import SimpleNamespace

from papertrans.desktop.windowing import DesktopWindowFrame, _Win32NativeApi


class _FakeNativeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def enable_resizable_frame(self, handle: int) -> None:
        self.calls.append(("enable", handle))

    def begin_move(self, handle: int) -> None:
        self.calls.append(("move", handle))

    def begin_resize(self, handle: int, hit_test: int) -> None:
        self.calls.append(("resize", handle, hit_test))

    def set_maximized(self, handle: int, maximized: bool) -> None:
        self.calls.append(("maximized", handle, maximized))


class _FakeUser32:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def SetWindowPos(self, *args: object) -> bool:
        self.calls.append(("frame_changed", *args))
        return True

    def ReleaseCapture(self) -> bool:
        self.calls.append(("release_capture",))
        return True

    def SendMessageW(self, *args: object) -> int:
        self.calls.append(("send_message", *args))
        return 0


class _FakeDwmApi:
    def __init__(self) -> None:
        self.settings: list[tuple[int, int]] = []

    def DwmSetWindowAttribute(
        self, _handle: int, _attribute: int, value: object, _size: int
    ) -> int:
        self.settings.append((_attribute, value._obj.value))
        return 0


def test_native_window_frame_maps_move_resize_and_rounding() -> None:
    native_api = _FakeNativeApi()
    frame = DesktopWindowFrame(native_api=native_api, ui_dispatch=lambda callback: callback())
    frame.attach(SimpleNamespace(native=SimpleNamespace(Handle=91)))

    assert frame.initialize() is True
    assert frame.begin_move() is True
    assert frame.begin_resize("northwest") is True
    assert frame.begin_resize("unknown") is False
    assert frame.set_maximized(True) is True
    assert frame.set_maximized(False) is True
    assert native_api.calls == [
        ("enable", 91),
        ("maximized", 91, False),
        ("move", 91),
        ("resize", 91, 13),
        ("maximized", 91, True),
        ("maximized", 91, False),
    ]


def test_resize_frame_is_only_enabled_during_native_move_and_resize() -> None:
    initial_style = 0x160B0000
    styles = [initial_style]
    user32 = _FakeUser32()
    native = _Win32NativeApi.__new__(_Win32NativeApi)
    native._user32 = user32
    native._get_style = lambda _handle, _index: styles[-1]
    native._set_style = lambda _handle, _index, style: styles.append(style)

    native.enable_resizable_frame(77)
    native.begin_move(77)
    native.begin_resize(77, 10)

    assert styles == [
        initial_style,
        initial_style,
        initial_style | native._WS_THICKFRAME,
        initial_style,
        initial_style | native._WS_THICKFRAME,
        initial_style,
    ]
    assert user32.calls[2] == ("release_capture",)
    assert user32.calls[3] == (
        "send_message",
        77,
        native._WM_NCLBUTTONDOWN,
        native._HTCAPTION,
        0,
    )
    assert user32.calls[6] == ("release_capture",)
    assert user32.calls[7] == ("send_message", 77, native._WM_NCLBUTTONDOWN, 10, 0)


def test_maximized_window_keeps_resize_frame_until_drag_restore_finishes() -> None:
    initial_style = 0x160B0000
    styles = [initial_style]
    user32 = _FakeUser32()
    dwmapi = _FakeDwmApi()
    native = _Win32NativeApi.__new__(_Win32NativeApi)
    native._user32 = user32
    native._dwmapi = dwmapi
    native._get_style = lambda _handle, _index: styles[-1]
    native._set_style = lambda _handle, _index, style: styles.append(style)

    native.set_maximized(77, True)
    native.begin_move(77)
    native.set_maximized(77, False)

    assert styles == [
        initial_style,
        initial_style | native._WS_THICKFRAME,
        initial_style,
    ]
    assert dwmapi.settings == [
        (native._DWMWA_WINDOW_CORNER_PREFERENCE, native._DWMWCP_DONOTROUND),
        (native._DWMWA_BORDER_COLOR, native._DWMWA_COLOR_NONE),
        (native._DWMWA_WINDOW_CORNER_PREFERENCE, native._DWMWCP_ROUND),
        (native._DWMWA_BORDER_COLOR, native._DWMWA_COLOR_NONE),
    ]
