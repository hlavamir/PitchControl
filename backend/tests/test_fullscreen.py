"""The macOS full screen (fullscreen.py, item 69): the menu bar and the Dock auto-hide instead of staying hidden, and
the borderless window still covers the whole screen. AppKit is not there on other platforms, so a stand-in is used."""

from __future__ import annotations

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

    def setPresentationOptions_(self, options):
        self.options.append(options)


class FakeNative:
    def __init__(self, screen):
        self._screen = screen
        self._frame = Rect(100, 100, 1200, 800)
        self.style = 15
        self.shadow = True
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

    def makeKeyAndOrderFront_(self, sender):
        self.calls.append("front")

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
    return fs, app, native


def test_the_option_values_are_the_auto_hide_ones():
    assert fullscreen._AUTO_HIDE_DOCK == AUTO_HIDE_DOCK == 1
    assert fullscreen._AUTO_HIDE_MENU_BAR == AUTO_HIDE_MENU_BAR == 4


def test_full_screen_auto_hides_the_menu_bar_and_the_dock_and_covers_the_screen(monkeypatch):
    fs, app, native = mac_fullscreen(monkeypatch)
    original = native.frame()
    fs._apply_mac(True)
    assert app.options == [AUTO_HIDE_DOCK | AUTO_HIDE_MENU_BAR]
    assert app.options[-1] & (HIDE_DOCK | HIDE_MENU_BAR) == 0  # hidden for good was the bug: the menus couldn't be reached
    assert native.frame() == Rect(0, 0, 1512, 982)  # the whole screen, notch strip and menu bar area included
    assert native.style == fullscreen._STYLE_BORDERLESS and native.shadow is False
    fs._apply_mac(False)
    assert app.options[-1] == 0  # back to the normal menu bar and Dock
    assert native.frame() == original and native.style == 15 and native.shadow is True
