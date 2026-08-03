from types import SimpleNamespace

from papertrans.desktop.app import DesktopBridge


class _FakeWindow:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def minimize(self) -> None:
        self.calls.append("minimize")

    def maximize(self) -> None:
        self.calls.append("maximize")

    def restore(self) -> None:
        self.calls.append("restore")

    def destroy(self) -> None:
        self.calls.append("destroy")


class _FakeFrame:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def attach(self, window: object) -> None:
        self.calls.append(("attach", window))

    def initialize(self) -> bool:
        self.calls.append("initialize")
        return True

    def begin_move(self) -> bool:
        self.calls.append("move")
        return True

    def begin_resize(self, edge: str) -> bool:
        self.calls.append(("resize", edge))
        return True

    def set_maximized(self, maximized: bool) -> bool:
        self.calls.append(("maximized", maximized))
        return True


def test_desktop_bridge_controls_frameless_window() -> None:
    frame = _FakeFrame()
    bridge = DesktopBridge(SimpleNamespace(), frame_controller=frame)  # type: ignore[arg-type]
    window = _FakeWindow()
    bridge.attach(window)

    assert bridge.initialize_window_frame() is True
    assert bridge.begin_window_drag() is True
    assert bridge.begin_window_resize("east") is True
    assert bridge.minimize_window() is True
    assert bridge.toggle_maximize_window() is True
    assert bridge.toggle_maximize_window() is False
    assert bridge.close_window() is True
    assert window.calls == ["minimize", "maximize", "restore", "destroy"]
    assert frame.calls == [
        ("attach", window),
        "initialize",
        "move",
        ("resize", "east"),
        ("maximized", True),
        ("maximized", False),
    ]
