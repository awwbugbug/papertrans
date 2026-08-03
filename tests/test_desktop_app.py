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


def test_desktop_bridge_controls_frameless_window() -> None:
    bridge = DesktopBridge(SimpleNamespace())  # type: ignore[arg-type]
    window = _FakeWindow()
    bridge.attach(window)

    assert bridge.minimize_window() is True
    assert bridge.toggle_maximize_window() is True
    assert bridge.toggle_maximize_window() is False
    assert bridge.close_window() is True
    assert window.calls == ["minimize", "maximize", "restore", "destroy"]
