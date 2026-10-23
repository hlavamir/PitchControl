"""The macOS full screen (fullscreen.py, items 69, 71, 72): the menu bar and the Dock are hidden for good (the page
draws the menu), the borderless window covers the whole screen and is the key window that takes mouse-moved events,
which the web view's hover needs. AppKit is not there on other platforms, so a stand-in is used."""

from __future__ import annotations

import logging
import sys
import types

import pitchcontrol.fullscreen as fullscreen
from pitchcontrol.fullscreen import Fullscreen

# NSApplicationPresentationOptions, from Apple's headers
AUTO_HIDE_DOCK = 1 << 0
HIDE_DOCK = 1 << 1
AUTO_HIDE_MENU_BAR = 1 << 2
HIDE_MENU_BAR = 1 << 3


class Rect:
    def __init__(self, x, y, w, h):
        self.origin = types.SimpleNamespace(x=x, y=y)
        self.size = types.SimpleNamespace(width=w, height=h)

    def __eq__(self, other):
        return (self.origin.x, self.origin.y, self.size.width, self.size.height) == (other.origin.x, other.origin.y, other.size.width, other.size.height)


class FakeApp:
    def __init__(self):
        self.options = []
        self.activated = 0

    def setPresentationOptions_(self, options):
        self.options.append(options)

    def activateIgnoringOtherApps_(self, flag):
        self.activated += 1

    def isActive(self):
        return True


class FakeNative:
    def __init__(self, screen):
        self._screen = screen
        self._frame = Rect(100, 100, 1200, 800)
        self.style = 15
        self.shadow = True
        self.mouse_moved = False
        self.key = False
        self.calls = []

    def frame(self):
        return self._frame

    def styleMask(self):
        return self.style

    def hasShadow(self):
        return self.shadow

    def screen(self):
        return self._screen

    def contentView(self):
        return "content"

    def setStyleMask_(self, mask):
        self.style = mask

    def setHasShadow_(self, on):
        self.shadow = on

    def setFrame_display_(self, rect, display):
        self._frame = rect

    def setAcceptsMouseMovedEvents_(self, on):
        self.mouse_moved = on

    def acceptsMouseMovedEvents(self):
        return self.mouse_moved

    def makeKeyAndOrderFront_(self, sender):
        self.key = True
        self.calls.append("front")

    def isKeyWindow(self):
        return self.key

    def makeFirstResponder_(self, view):
        self.calls.append("responder")


def mac_fullscreen(monkeypatch):
    app = FakeApp()
    appkit = types.SimpleNamespace(
        NSApplication=types.SimpleNamespace(sharedApplication=lambda: app),
        NSScreen=types.SimpleNamespace(mainScreen=lambda: None),
    )
    monkeypatch.setitem(sys.modules, "AppKit", appkit)
    screen = types.SimpleNamespace(frame=lambda: Rect(0, 0, 1512, 982))  # a 14" MacBook with the notch: the whole panel
    native = FakeNative(screen)
    fs = Fullscreen(types.SimpleNamespace(native=native))
    fs.mac = True
    fs._later = lambda seconds, fn: fn()  # the settle check runs at once
    return fs, app, native


def test_the_option_values_are_the_hide_ones():
    assert fullscreen._HIDE_DOCK == HIDE_DOCK == 2
    assert fullscreen._HIDE_MENU_BAR == HIDE_MENU_BAR == 8


def test_full_screen_hides_the_menu_bar_and_the_dock_and_covers_the_screen(monkeypatch):
    fs, app, native = mac_fullscreen(monkeypatch)
    original = native.frame()
    fs.active = True
    fs._apply_mac(True)
    # hidden for good (item 72): an auto-hiding menu bar waits for the mouse in the header's top row, where the bubbles'
    # indicators are (item 71); the menus are the page's own drawn menu
    assert app.options == [HIDE_DOCK | HIDE_MENU_BAR]
    assert app.options[-1] & (AUTO_HIDE_DOCK | AUTO_HIDE_MENU_BAR) == 0
    assert native.frame() == Rect(0, 0, 1512, 982)  # the whole screen, notch strip and menu bar area included
    assert native.style == fullscreen._STYLE_BORDERLESS and native.shadow is False
    fs._apply_mac(False)
    assert app.options[-1] == 0  # back to the normal menu bar and Dock
    assert native.frame() == original and native.style == 15 and native.shadow is True


def test_the_borderless_window_is_key_and_takes_mouse_moved_events(monkeypatch, caplog):
    fs, app, native = mac_fullscreen(monkeypatch)
    fs.active = True
    with caplog.at_level(logging.INFO, logger="pitchcontrol.fullscreen"):
        fs._apply_mac(True)
    assert native.mouse_moved is True  # the web view's hover (bubbles, footer hints) needs mouse-moved events
    assert native.key and app.activated >= 1  # ... in the key window of the active app, asked again once settled
    assert native.calls.count("front") == 2 and native.calls[-1] == "responder"
    assert any("key window True, app active True, accepts mouse moved True" in r.message for r in caplog.records)
