from types import SimpleNamespace

from papertrans.desktop.windowing import DesktopWindowFrame


class _FakeNativeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def enable_resizable_frame(self, handle: int) -> None:
        self.calls.append(("enable", handle))

    def begin_move(self, handle: int) -> None:
        self.calls.append(("move", handle))

    def begin_resize(self, handle: int, hit_test: int) -> None:
        self.calls.append(("resize", handle, hit_test))

    def set_rounded(self, handle: int, rounded: bool) -> None:
        self.calls.append(("rounded", handle, rounded))


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
        ("rounded", 91, True),
        ("move", 91),
        ("resize", 91, 13),
        ("rounded", 91, False),
        ("rounded", 91, True),
    ]
