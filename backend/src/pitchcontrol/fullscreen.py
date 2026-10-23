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
_RETAKE_AFTER = (0.3, 1.5, 4.0)  # seconds after full screen starts: the window has settled, the page has loaded, the app is active


class Fullscreen:
    def __init__(self, window):
        self.window = window  # pywebview Window
        self.active = False
        self._saved: tuple | None = None  # (frame, style mask, shadow) to restore
        self._lock = threading.Lock()
        self.mac = sys.platform == "darwin"
        self._area: tuple | None = None  # (view, tracking area, owner) of _watch_mouse
        self._generation = 0  # counts the entries and exits: a delayed check belongs to one

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
        try:
            self.window.events.loaded += self._on_loaded
        except Exception:  # noqa: BLE001
            log.exception("full screen: can't listen for the page loading")

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
        self._generation += 1  # the delayed checks of an earlier entry or exit stop
        generation = self._generation
        if on:
            self._saved = (ns.frame(), ns.styleMask(), ns.hasShadow())
            app.setPresentationOptions_(_HIDE_DOCK | _HIDE_MENU_BAR)
            ns.setStyleMask_(_STYLE_BORDERLESS)
            # the window shadow includes a 1 px outline, visible at the rounded screen corners
            ns.setHasShadow_(False)
            screen = ns.screen() or AppKit.NSScreen.mainScreen()
            ns.setFrame_display_(screen.frame(), True)
            log.info("full screen on: window %s, screen %s, shadow %s", _size(ns.frame()), _size(screen.frame()), ns.hasShadow())
        else:
            frame, style, shadow = self._saved or (ns.frame(), ns.styleMask(), True)
            ns.setStyleMask_(style)
            ns.setHasShadow_(shadow)
            ns.setFrame_display_(frame, True)
            app.setPresentationOptions_(0)
            log.info("full screen off: window %s", _size(ns.frame()))
        # a style mask change can leave the web view in the window without mouse tracking, key state and focus, so every
        # entry and every exit does the same: the web view is put in the window again, the mouse is taken, and that is
        # repeated later (item 72: after leaving full screen and entering it again the menu stopped reacting to hover)
        self._remount(ns)
        self._take_the_mouse(ns, app, report=True)
        for seconds in _RETAKE_AFTER:
            self._later(seconds, lambda: self._retake(generation))

    def _later(self, seconds: float, fn) -> None:
        from PyObjCTools import AppHelper

        AppHelper.callLater(seconds, fn)

    def _take_the_mouse(self, ns, app, report: bool = False) -> None:
        """The borderless window is the key window of the active app and takes mouse-moved events: the web view's
        hover (the header's bubbles, the footer hints, the drawn menu) needs all three, and the web view is the first
        responder. A style mask change can leave the window without the key, and when the app starts in full screen
        this all runs before the web view is the window's content view (pywebview adds it when the page has loaded),
        so it is asked again: when the page has loaded, after a few seconds, and when the mouse first enters the
        window (items 71 and 72: after a start in full screen the menu didn't react to the mouse until a key press).
        The state is logged."""
        app.activateIgnoringOtherApps_(True)
        ns.setAcceptsMouseMovedEvents_(True)
        ns.makeKeyAndOrderFront_(None)
        ns.makeFirstResponder_(ns.contentView())
        self._watch_mouse(ns, app)
        if report:
            log.info(
                "full screen %s: key window %s, app active %s, accepts mouse moved %s, web view first responder %s",
                "on" if self.active else "off",
                ns.isKeyWindow(),
                app.isActive(),
                ns.acceptsMouseMovedEvents(),
                ns.firstResponder() == ns.contentView(),
            )

    def _remount(self, ns) -> None:
        """Put the web view in the window again (the way pywebview does when the page has loaded, which is the state in
        which hover worked after a start in full screen): swap another view in and the web view back, then no first
        responder and the tracking area again. Not before the page has loaded: pywebview mounts it itself then."""
        view = ns.contentView()
        if getattr(view, "pywebview_window", None) is None:
            return
        try:
            import AppKit

            self._unwatch_mouse()
            try:
                ns.setContentView_(AppKit.NSView.alloc().init())
            finally:
                ns.setContentView_(view)
            ns.makeFirstResponder_(None)
        except Exception:  # noqa: BLE001
            log.exception("full screen: can't put the web view in the window again")

    def _retake(self, generation: int | None = None) -> None:
        """The same again, later (main thread): nothing if full screen was entered or left meanwhile."""
        import AppKit

        ns = self.window.native
        if ns is not None and (generation is None or generation == self._generation):
            self._take_the_mouse(ns, AppKit.NSApplication.sharedApplication(), report=True)

    def _on_loaded(self) -> None:
        """The page has loaded (a thread of pywebview's): the web view is the content view now."""
        if self.active:
            self._on_main(self._retake)

    def _mouse_entered(self) -> None:
        """The mouse came into the window (main thread). The window isn't key, doesn't take mouse-moved events or the
        web view isn't the first responder: take the mouse again, and say so in the log."""
        import AppKit

        ns = self.window.native
        if ns is None:
            return
        view = ns.contentView()
        if ns.isKeyWindow() and ns.acceptsMouseMovedEvents() and ns.firstResponder() == view:
            return
        log.info("full screen: the mouse entered a window that was not ready (key %s, mouse moved %s): asking again", ns.isKeyWindow(), ns.acceptsMouseMovedEvents())
        self._take_the_mouse(ns, AppKit.NSApplication.sharedApplication(), report=True)

    def _watch_mouse(self, ns, app) -> None:
        """A tracking area that is active whether or not the window is key, on the content view: its mouse-entered
        event calls ``_mouse_entered``. Moved to the new content view when pywebview swaps it in."""
        try:
            import AppKit

            view = ns.contentView()
            if self._area is not None and self._area[0] == view:
                return
            self._unwatch_mouse()
            owner = _entered_owner()
            owner.fullscreen = self
            options = AppKit.NSTrackingMouseEnteredAndExited | AppKit.NSTrackingActiveAlways | AppKit.NSTrackingInVisibleRect
            area = AppKit.NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(view.bounds(), options, owner, None)
            view.addTrackingArea_(area)
            self._area = (view, area, owner)
        except Exception:  # noqa: BLE001
            log.exception("full screen: can't watch for the mouse entering the window")

    def _unwatch_mouse(self) -> None:
        if self._area is not None:
            view, area, _ = self._area
            self._area = None
            try:
                view.removeTrackingArea_(area)
            except Exception:  # noqa: BLE001
                log.exception("full screen: can't remove the mouse watcher")


_owner_class = None


def _entered_owner():
    """An Objective-C object that gets the tracking area's mouseEntered_ (the class is made once, on first use)."""
    global _owner_class
    import AppKit

    if _owner_class is None:

        class MouseEntered(AppKit.NSObject):
            def mouseEntered_(self, event):
                try:
                    self.fullscreen._mouse_entered()
                except Exception:  # noqa: BLE001
                    log.exception("full screen: mouse entered")

        _owner_class = MouseEntered
    return _owner_class.alloc().init()


def _size(rect) -> str:
    return f"{rect.size.width:.0f}x{rect.size.height:.0f} at ({rect.origin.x:.0f},{rect.origin.y:.0f})"
