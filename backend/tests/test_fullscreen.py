"""Full screen (fullscreen.py, item 78): macOS uses the window's own native full screen, the one behind the green button
and ⌃⌘F, and keeps its state from the window's notifications; other platforms use pywebview's. AppKit is not there on
other platforms, so a stand-in is used."""

from __future__ import annotations

import logging
import sys
import types

from pitchcontrol.fullscreen import Fullscreen

STYLE_FULLSCREEN = 1 << 14  # NSWindowStyleMaskFullScreen, from Apple's headers
BEHAVIOR_MANAGED = 1 << 2
BEHAVIOR_FULLSCREEN_PRIMARY = 1 << 7


class Rect:
    def __init__(self, x, y, w, h):
        self.origin = types.SimpleNamespace(x=x, y=y)
        self.size = types.SimpleNamespace(width=w, height=h)


class FakeNative:
    """A window: toggleFullScreen_ flips the full screen bit, as AppKit does when the transition starts."""

    def __init__(self):
        self.style = 15
        self.behavior = None
        self.toggles = 0
        self._frame = Rect(100, 100, 1200, 800)

    def styleMask(self):
        return self.style

    def frame(self):
        return self._frame

    def setCollectionBehavior_(self, behavior):
        self.behavior = behavior

    def toggleFullScreen_(self, sender):
        self.toggles += 1
        self.style ^= STYLE_FULLSCREEN


class FakeCenter:
    def __init__(self):
        self.observers = {}

    def addObserverForName_object_queue_usingBlock_(self, name, obj, queue, block):
        self.observers[name] = block
        return object()

    def post(self, name):
        self.observers[name](None)


def mac_fullscreen(monkeypatch):
    center = FakeCenter()
    appkit = types.SimpleNamespace(NSNotificationCenter=types.SimpleNamespace(defaultCenter=lambda: center))
    monkeypatch.setitem(sys.modules, "AppKit", appkit)
    native = FakeNative()
    fs = Fullscreen(types.SimpleNamespace(native=native))
    fs.mac = True
    fs._on_main = lambda fn: fn()
    return fs, native, center


ENTER, EXIT = "NSWindowDidEnterFullScreenNotification", "NSWindowDidExitFullScreenNotification"


def test_the_green_button_becomes_full_screen(monkeypatch):
    fs, native, _ = mac_fullscreen(monkeypatch)
    fs.setup()
    assert native.behavior == BEHAVIOR_MANAGED | BEHAVIOR_FULLSCREEN_PRIMARY


def test_set_uses_the_windows_own_full_screen_and_nothing_else(monkeypatch):
    fs, native, _ = mac_fullscreen(monkeypatch)
    assert fs.set(True) is True
    assert native.toggles == 1 and native.style & STYLE_FULLSCREEN
    assert native.style & ~STYLE_FULLSCREEN == 15  # no style mask change of ours: the window stays as it is
    assert fs.set(False) is False
    assert native.toggles == 2 and not native.style & STYLE_FULLSCREEN


def test_asking_for_the_state_it_is_in_does_nothing(monkeypatch):
    fs, native, _ = mac_fullscreen(monkeypatch)
    fs.set(False)
    assert native.toggles == 0
    fs.set(True)
    fs.set(True)
    assert native.toggles == 1


def test_a_window_that_is_in_full_screen_already_is_not_toggled_out_again(monkeypatch):
    """The green button was faster than the page: the window is in full screen, ``active`` not yet told."""
    fs, native, _ = mac_fullscreen(monkeypatch)
    native.style |= STYLE_FULLSCREEN
    fs.set(True)
    assert native.toggles == 0 and fs.active


def test_the_state_follows_the_window_whoever_changes_it(monkeypatch, caplog):
    fs, native, center = mac_fullscreen(monkeypatch)
    fs.setup()
    with caplog.at_level(logging.INFO, logger="pitchcontrol.fullscreen"):
        center.post(ENTER)  # the green button or ⌃⌘F
        assert fs.active
        center.post(EXIT)
        assert not fs.active
    assert "full screen on: window 1200x800 at (100,100)" in caplog.text
    assert "full screen off" in caplog.text and "off: window" not in caplog.text  # leaving: the frame is the animation's


def test_toggle_after_the_window_changed_by_itself(monkeypatch):
    fs, native, center = mac_fullscreen(monkeypatch)
    fs.setup()
    native.style |= STYLE_FULLSCREEN
    center.post(ENTER)
    assert fs.toggle() is False  # one press of F leaves it
    assert native.toggles == 1 and not native.style & STYLE_FULLSCREEN


def test_no_window_is_no_error(monkeypatch):
    fs, _, _ = mac_fullscreen(monkeypatch)
    fs.window = types.SimpleNamespace(native=None)
    fs.setup()
    fs.set(True)


def test_other_platforms_use_pywebviews_full_screen():
    calls = []
    window = types.SimpleNamespace(toggle_fullscreen=lambda: calls.append("toggle"), native=None)
    fs = Fullscreen(window)
    fs.mac = False
    fs.setup()  # nothing to set up
    assert fs.set(True) is True and fs.active
    assert fs.set(True) is True  # already there
    assert fs.toggle() is False
    assert calls == ["toggle", "toggle"]
