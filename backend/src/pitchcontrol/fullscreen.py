"""Full screen for the desktop app.

macOS uses the system's own full screen (item 78), the one behind the green window button and ⌃⌘F: the window moves to
its own Space, the menu bar slides in at the top edge and the Dock at the bottom, and on a MacBook with a camera notch
the window sits below the notch (the strip beside the notch stays black, so the picture is about 33 px shorter). Items
69 to 72 tried PitchControl's own borderless full screen instead, to use the notch strip, and the web view's hover
broke in it (WebKit's mouse tracking after the style mask change); the native one has none of that.

The window enters and leaves full screen by itself too (the green button, ⌃⌘F), so the state is kept from the window's
notifications, not from what this module asked for.

Other platforms use pywebview's own full screen.
"""

from __future__ import annotations

import logging
import sys
import threading

log = logging.getLogger(__name__)

# AppKit constants (kept numeric so this module imports without AppKit on other platforms)
_STYLE_FULLSCREEN = 1 << 14  # NSWindowStyleMaskFullScreen: set while the window is (entering) full screen
_BEHAVIOR_MANAGED = 1 << 2  # NSWindowCollectionBehaviorManaged
_BEHAVIOR_FULLSCREEN_PRIMARY = 1 << 7  # NSWindowCollectionBehaviorFullScreenPrimary: the green button = full screen
_NOTIFICATIONS = (("NSWindowDidEnterFullScreenNotification", True), ("NSWindowDidExitFullScreenNotification", False))


class Fullscreen:
    def __init__(self, window):
        self.window = window  # pywebview Window
        self.active = False
        self._lock = threading.Lock()
        self.mac = sys.platform == "darwin"
        self._observers: list = []  # the window's notification observers (kept alive)

    # -- helpers
    def _on_main(self, fn) -> None:
        from PyObjCTools import AppHelper

        AppHelper.callAfter(fn)

    def setup(self) -> None:
        """After the window is shown (macOS): the green button is full screen, and ``active`` follows the window."""
        if not self.mac:
            return

        def apply():
            import AppKit

            ns = self.window.native
            if ns is None:
                return
            ns.setCollectionBehavior_(_BEHAVIOR_MANAGED | _BEHAVIOR_FULLSCREEN_PRIMARY)
            center = AppKit.NSNotificationCenter.defaultCenter()
            for name, on in _NOTIFICATIONS:
                self._observers.append(center.addObserverForName_object_queue_usingBlock_(name, ns, None, lambda note, on=on: self._changed(on)))

        self._on_main(apply)

    def _changed(self, on: bool) -> None:
        """The window has entered or left full screen (main thread)."""
        self.active = on
        ns = self.window.native
        # the size only on entering: the frame at the end of leaving is still the animation's (3008 wide with a second screen)
        log.info("full screen on: window %s", _size(ns.frame())) if on and ns is not None else log.info("full screen %s", "on" if on else "off")

    # -- public
    def set(self, on: bool) -> bool:
        with self._lock:
            if on == self.active:
                return self.active
            self.active = on
        if not self.mac:
            self.window.toggle_fullscreen()
            return on
        self._on_main(lambda: self._apply_mac(on))
        return on

    def toggle(self) -> bool:
        return self.set(not self.active)

    def _apply_mac(self, on: bool) -> None:
        ns = self.window.native
        if ns is not None and bool(ns.styleMask() & _STYLE_FULLSCREEN) != on:  # it may be there already (the green button)
            ns.toggleFullScreen_(None)


def _size(rect) -> str:
    return f"{rect.size.width:.0f}x{rect.size.height:.0f} at ({rect.origin.x:.0f},{rect.origin.y:.0f})"
