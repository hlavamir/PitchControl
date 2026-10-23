"""Full screen for the desktop app.

macOS native full screen keeps windows below the camera notch of newer MacBooks and paints the
strip beside it black. Instead, PitchControl hides the menu bar and Dock and stretches a borderless
window over the whole screen, notch strip included; the UI keeps that 32 px strip free in the middle
(top header row: logo left, indicators right). The green window button becomes a plain zoom.

The menu bar and the Dock are hidden for good, as before item 69. Item 69 auto-hid them instead (the menu bar slides in
at the top edge), and the 1.8.2 check on a Mac showed what that costs: the menus were still out of reach, and the
header's hover bubbles (item 66) stopped showing, whose indicators sit in the very strip where an auto-hidden menu bar
waits for the mouse (item 71). The menus come back as the UI's own drawn menu next to the logo, as on Windows
(item 72, ``menu.py``): the page shows it while ``/api/app-info`` says ``fullscreen``.

Other platforms use pywebview's own full screen (no notch there).
"""

from __future__ import annotations

import logging
import sys
import threading

log = logging.getLogger(__name__)

# AppKit constants (kept numeric so this module imports without AppKit on other platforms)
_HIDE_DOCK = 1 << 1  # NSApplicationPresentationHideDock
_HIDE_MENU_BAR = 1 << 3  # NSApplicationPresentationHideMenuBar
_STYLE_BORDERLESS = 0  # NSWindowStyleMaskBorderless
_FULLSCREEN_NONE = 1 << 9  # NSWindowCollectionBehaviorFullScreenNone: green button = zoom


class Fullscreen:
    def __init__(self, window):
        self.window = window  # pywebview Window
        self.active = False
        self._saved: tuple | None = None  # (frame, style mask, shadow) to restore
        self._lock = threading.Lock()
        self.mac = sys.platform == "darwin"

    # -- helpers
    def _on_main(self, fn) -> None:
        from PyObjCTools import AppHelper

        AppHelper.callAfter(fn)

    def setup(self) -> None:
        """After the window is shown: route the green button to zoom instead of native full screen."""
        if not self.mac:
            return

        def apply():
            ns = self.window.native
            if ns is not None:
                ns.setCollectionBehavior_(_FULLSCREEN_NONE)

        self._on_main(apply)

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
        import AppKit

        ns = self.window.native
        if ns is None:
            return
        app = AppKit.NSApplication.sharedApplication()
        if on:
            self._saved = (ns.frame(), ns.styleMask(), ns.hasShadow())
            app.setPresentationOptions_(_HIDE_DOCK | _HIDE_MENU_BAR)
            ns.setStyleMask_(_STYLE_BORDERLESS)
            # the window shadow includes a 1 px outline, visible at the rounded screen corners
            ns.setHasShadow_(False)
            screen = ns.screen() or AppKit.NSScreen.mainScreen()
            ns.setFrame_display_(screen.frame(), True)
            self._take_the_mouse(ns, app)
            log.info("full screen on: window %s, screen %s, shadow %s", _size(ns.frame()), _size(screen.frame()), ns.hasShadow())
            self._later(0.3, lambda: self._take_the_mouse(ns, app, report=True))
        else:
            frame, style, shadow = self._saved or (ns.frame(), ns.styleMask(), True)
            ns.setStyleMask_(style)
            ns.setHasShadow_(shadow)
            ns.setFrame_display_(frame, True)
            app.setPresentationOptions_(0)
            ns.makeFirstResponder_(ns.contentView())
            log.info("full screen off: window %s", _size(ns.frame()))


    def _later(self, seconds: float, fn) -> None:
        from PyObjCTools import AppHelper

        AppHelper.callLater(seconds, fn)

    def _take_the_mouse(self, ns, app, report: bool = False) -> None:
        """The borderless window is the key window of the active app and takes mouse-moved events: the web view's
        hover (the header's bubbles, the footer hints) needs all three. A style mask change can leave the window
        without the key, so it is asked again once the change has settled, and the state is logged (item 71)."""
        app.activateIgnoringOtherApps_(True)
        ns.setAcceptsMouseMovedEvents_(True)
        ns.makeKeyAndOrderFront_(None)
        ns.makeFirstResponder_(ns.contentView())
        if report and self.active:
            log.info("full screen: key window %s, app active %s, accepts mouse moved %s", ns.isKeyWindow(), app.isActive(), ns.acceptsMouseMovedEvents())


def _size(rect) -> str:
    return f"{rect.size.width:.0f}x{rect.size.height:.0f} at ({rect.origin.x:.0f},{rect.origin.y:.0f})"
