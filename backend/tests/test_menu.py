"""The menu bar (item 52): one definition for macOS and Windows (``menu.py``) and its actions."""

import sys
import types

import pytest
from fastapi.testclient import TestClient

from pitchcontrol import menu as menu_module
from pitchcontrol.config.models import NetworkSettings
from pitchcontrol.engine.engine import Engine
from pitchcontrol.menu import DISCORD_URL, DOCS_URL, PAGES, SEPARATOR, MenuActions, Submenu, arrange_cocoa_menu, items_by_id, key_equivalent, menu_json, menus_for, native_menu, walk
from pitchcontrol.server.app import create_app

PHONE = ("192.168.1.50", 50000)


def titles(platform):
    return [title for title, _ in menus_for(platform)]


def labels(platform, title):
    return [None if i is SEPARATOR else i.label for t, items in menus_for(platform) if t == title for i in items]


def test_one_definition_for_both_platforms():
    assert titles("mac") == ["PitchControl", "File", "Edit", "View", "Window", "Help"]
    assert titles("win") == ["File", "Edit", "View", "Window", "Help"]  # no application menu on Windows
    assert labels("win", "File") == ["Save", None, "Import Fixture", None, "Open data folder", "Open logs folder", None, "Quit"]
    assert labels("mac", "File") == ["Save", None, "Import Fixture", None, "Open data folder", "Open logs folder"]  # Quit ⌘Q is in the application menu
    assert labels("mac", "PitchControl") == ["About PitchControl", "Settings…"]
    assert labels("win", "Edit") == labels("mac", "Edit") == ["Cut", "Copy", "Paste", None, "Select All"]
    assert labels("win", "View") == [*PAGES, None, "Full screen"]
    assert labels("mac", "Window") == ["Minimize", "Zoom"]
    assert labels("win", "Window") == ["Minimize", "Maximize"]
    assert labels("win", "Help") == ["Documentation", "Keyboard shortcuts", None, "Show log", "Report a problem", "Join the Discord", None, "About PitchControl"]
    assert labels("mac", "Help") == ["Documentation", "Keyboard shortcuts", None, "Show log", "Report a problem", "Join the Discord"]
    # same item, same action on both platforms: an id has one meaning
    for platform in ("mac", "win"):
        ids = [i.id for _, items in menus_for(platform) for i in walk(items)]
        assert len(ids) == len(set(ids))
        assert all(i in items_by_id() for i in ids)


def test_no_stray_separators():
    for platform in ("mac", "win"):
        for title, items in menus_for(platform):
            assert items[0] is not SEPARATOR and items[-1] is not SEPARATOR, title
            assert all(not (a is SEPARATOR and b is SEPARATOR) for a, b in zip(items, items[1:])), title


def test_keys_shown_and_bound():
    win = {i["id"]: i["key"] for m in menu_json("win") for i in m["items"] if i and "id" in i}
    assert win["file.save"] == "Ctrl+S"
    assert win["view.page.1"] == "1" and win["view.page.9"] == "9"  # the app's own page keys
    assert win["view.page.0"] == "0"  # Help
    assert win["view.fullscreen"] == "F"
    assert win["edit.copy"] == "Ctrl+C"
    mac = {i.id: i.mac_key for _, items in menus_for("mac") for i in walk(items)}
    assert mac["file.save"] == "cmd+s"
    assert mac["view.page.3"] == "cmd+3"  # ⌘3 next to the plain 3
    assert mac["view.page.0"] == ""  # ⌘0 is the UI scale's 100 %
    assert mac["app.settings"] == "cmd+,"
    assert mac["view.fullscreen"] == "ctrl+cmd+f"
    assert mac["window.minimize"] == "cmd+m"
    assert key_equivalent("ctrl+cmd+f") == ("f", (1 << 18) | (1 << 20))
    assert key_equivalent("cmd+,") == (",", 1 << 20)


def test_kinds():
    by_id = items_by_id()
    assert {i for i, item in by_id.items() if item.kind == "native"} == {"edit.cut", "edit.copy", "edit.paste", "edit.select_all"}
    assert by_id["file.save"].kind == "ui"  # the page's own Save
    assert by_id["view.page.4"].kind == "ui"
    assert by_id["file.quit"].kind == "app"  # through the quit guard


def test_file_import_fixture_is_a_submenu_with_the_open_fixture_library_and_qlcplus():
    """File → Import Fixture ▸ Open Fixture Library… (item 53) and QLC+… (item 54)."""
    for platform in ("mac", "win"):
        (file_items,) = [items for t, items in menus_for(platform) if t == "File"]
        (sub,) = [i for i in file_items if isinstance(i, Submenu)]
        assert sub.label == "Import Fixture" and [i.label for i in sub.items] == ["Open Fixture Library…", "QLC+…"]
    assert items_by_id()["file.import.ofl"].kind == "ui"  # the Fixtures page's dialog
    assert items_by_id()["file.import.qlc"].kind == "ui"
    file_menu = next(m for m in menu_json("win") if m["title"] == "File")
    assert {
        "submenu": "Import Fixture",
        "items": [
            {"id": "file.import.ofl", "label": "Open Fixture Library…", "kind": "ui", "key": ""},
            {"id": "file.import.qlc", "label": "QLC+…", "kind": "ui", "key": ""},
        ],
    } in file_menu["items"]


def test_the_native_macos_menu_nests_the_submenu():
    from webview.menu import Menu, MenuAction

    file_menu = next(m for m in native_menu(MenuActions("/d", "/l")) if m.title == "File")
    nested = next(i for i in file_menu.items if isinstance(i, Menu))
    assert nested.title == "Import Fixture" and [i.title for i in nested.items] == ["Open Fixture Library…", "QLC+…"]
    assert all(isinstance(i, MenuAction) for i in nested.items)


def test_importing_from_the_native_menu_asks_the_page():
    window = FakeWindow()
    for item in ("file.import.ofl", "file.import.qlc"):
        window.calls.clear()
        MenuActions("/d", "/l", window=window).run(item)
        assert window.calls == [("js", f"window.pitchMenu && window.pitchMenu('{item}')")]


class FakeWindow:
    def __init__(self):
        self.calls = []

    def evaluate_js(self, script):
        self.calls.append(("js", script))

    def destroy(self):
        self.calls.append(("destroy",))

    def minimize(self):
        self.calls.append(("minimize",))

    def maximize(self):
        self.calls.append(("maximize",))

    def restore(self):
        self.calls.append(("restore",))


def actions(window=None):
    opened, revealed = [], []
    a = MenuActions("/data", "/logs", window=window, opener=opened.append, revealer=revealed.append)
    return a, opened, revealed


def test_app_actions():
    window = FakeWindow()
    a, opened, revealed = actions(window)
    a.run("file.data_folder")
    a.run("file.logs_folder")
    assert revealed == ["/data", "/logs"]
    a.run("help.docs")
    a.run("help.discord")
    assert opened == [DOCS_URL, DISCORD_URL]
    a.run("window.minimize")
    a.zoomed = False
    a.run("window.maximize")
    a.zoomed = True
    a.run("window.maximize")  # maximized already: back to the normal size
    assert window.calls == [("minimize",), ("maximize",), ("restore",)]


def test_quit_closes_the_window_so_the_quit_guard_asks():
    window = FakeWindow()
    a, _, _ = actions(window)
    a.run("file.quit")
    for t in __import__("threading").enumerate():
        if t.name == "menu-quit":
            t.join(2)
    # destroy() closes the window, which runs desktop.py's on_closing (the quit guard), like the close button
    assert window.calls == [("destroy",)]


def test_ui_items_go_to_the_page():
    window = FakeWindow()
    a, _, _ = actions(window)
    a.run("file.save")
    a.run("view.page.2")
    assert window.calls == [("js", "window.pitchMenu && window.pitchMenu('file.save')"), ("js", "window.pitchMenu && window.pitchMenu('view.page.2')")]


def test_unknown_and_native_items():
    a, _, _ = actions(FakeWindow())
    with pytest.raises(KeyError):
        a.run("file.nothing")
    with pytest.raises(ValueError):
        a.run("edit.copy")  # the system's (macOS) or the page's (Windows)


def test_menu_endpoints(store, monkeypatch):
    engine = Engine(store, enable_hardware=False)
    # not the desktop app (from source, a browser): the definition is there, running an item isn't
    plain = TestClient(create_app(engine), client=("127.0.0.1", 1))
    body = plain.get("/api/menu").json()
    assert [m["title"] for m in body["menus"]] == titles(body["platform"])
    assert plain.post("/api/menu/file.data_folder").status_code == 404

    a, opened, revealed = actions(FakeWindow())
    client = TestClient(create_app(engine, desktop={"url": "http://127.0.0.1:1", "data_dir": "/data", "menu": a}), client=("127.0.0.1", 1))
    assert client.post("/api/menu/file.data_folder").status_code == 200
    assert client.post("/api/menu/help.discord").status_code == 200
    assert revealed == ["/data"] and opened == [DISCORD_URL]
    assert client.post("/api/menu/nothing").status_code == 404
    assert client.post("/api/menu/edit.paste").status_code == 400
    assert client.get("/api/app-info").json()["platform"] == sys.platform


def test_menu_is_not_for_a_device_on_the_network(store):
    store.settings = store.settings.model_copy(update={"network": NetworkSettings(enabled=True)})
    a, opened, revealed = actions(FakeWindow())
    app = create_app(Engine(store, enable_hardware=False), desktop={"url": "http://127.0.0.1:1", "data_dir": "/data", "menu": a})
    phone = TestClient(app, client=PHONE)
    assert phone.get("/api/app-info").json()["local"] is False  # the UI draws no menu (appMenu.ts: showDrawnMenu)
    assert phone.get("/api/menu").status_code == 403
    assert phone.post("/api/menu/file.data_folder").status_code == 403
    assert phone.post("/api/menu/file.quit").status_code == 403
    assert opened == revealed == [] and a.window.calls == []


# ---- the macOS menu bar, arranged with stand-ins for AppKit's NSMenu and NSMenuItem


class NSItem:
    def __init__(self, title="", action=None, submenu=None):
        self._title, self._action, self._submenu = title, action, submenu
        self.key, self.mask, self.target, self.represented = "", 0, None, None

    def title(self):
        return self._title

    def setTitle_(self, t):
        self._title = t

    def action(self):
        return self._action

    def setAction_(self, a):
        self._action = a.encode()

    def submenu(self):
        return self._submenu

    def setKeyEquivalent_(self, k):
        self.key = k

    def setKeyEquivalentModifierMask_(self, m):
        self.mask = m

    def setTarget_(self, t):
        self.target = t

    def setRepresentedObject_(self, o):
        self.represented = o


class NSMenu:
    def __init__(self, title="", items=()):
        self._title, self.items = title, list(items)

    def title(self):
        return self._title

    def numberOfItems(self):
        return len(self.items)

    def itemAtIndex_(self, i):
        return self.items[i]

    def removeItem_(self, item):
        self.items.remove(item)

    def insertItem_atIndex_(self, item, i):
        self.items.insert(i, item)


def sub(title, *items):
    return NSItem(title, submenu=NSMenu(title, items))


def pywebview_menu_bar():
    """What pywebview builds on macOS with SHOW_DEFAULT_MENUS: App, its Edit and View, then ours."""
    app = sub("", NSItem("About", b"orderFrontStandardAboutPanel:"), NSItem("Settings…", b"handleMenuAction:"), NSItem("Quit", b"terminate:"))
    edit = sub("Edit", *(NSItem(t, s) for t, s in [("Cut", b"cut:"), ("Copy", b"copy:"), ("Paste", b"paste:"), ("Select All", b"selectAll:")]))
    default_view = sub("View", NSItem("Enter Full Screen", b"toggleFullScreen:"))
    ours = [sub(t, *(NSItem(i.label, b"handleMenuAction:") for i in items if i is not SEPARATOR)) for t, items in menus_for("mac") if t not in ("PitchControl", "Edit")]
    return NSMenu("", [app, edit, default_view, *ours])


def test_macos_menu_bar_is_arranged(monkeypatch):
    handler = types.SimpleNamespace(actions={}, register_action=lambda i, f: handler.actions.__setitem__(i, f))
    fake = types.ModuleType("webview.platforms.cocoa")
    fake.menu_handler = handler
    monkeypatch.setitem(sys.modules, "webview.platforms.cocoa", fake)
    bar = pywebview_menu_bar()
    about = []
    arrange_cocoa_menu(bar, about=lambda: about.append(1))
    assert [i.submenu().title() for i in bar.items] == ["", "File", "Edit", "View", "Window", "Help"]  # pywebview's View is gone

    def item(menu, label):
        return next(i for m in bar.items if m.submenu().title() == menu for i in m.submenu().items if i.title() == label)

    assert (item("File", "Save").key, item("File", "Save").mask) == ("s", 1 << 20)
    assert (item("View", "Rig").key, item("View", "Rig").mask) == ("4", 1 << 20)
    assert item("View", "Full screen").mask == (1 << 18) | (1 << 20)
    assert item("Window", "Minimize").key == "m"
    assert item("", "Settings…").key == ","
    assert item("Edit", "Copy").action() == b"copy:"  # native: ⌘C in text fields
    # About: the app's own (Settings → About, with the full version)
    about_item = item("", "About PitchControl")
    assert about_item.target is handler and about_item.action() == b"handleMenuAction:"
    handler.actions[about_item.represented]()
    assert about == [1]


def test_macos_arrangement_failure_keeps_pywebviews_menu(monkeypatch):
    calls = []

    class BrowserView:
        def _recreate_menus(self, user_menu):
            calls.append(user_menu)
            return "menu bar"

    fake = types.ModuleType("webview.platforms.cocoa")
    fake.BrowserView = BrowserView
    monkeypatch.setitem(sys.modules, "webview.platforms.cocoa", fake)
    monkeypatch.setattr(menu_module, "arrange_cocoa_menu", lambda *a, **k: 1 / 0)
    menu_module.patch_cocoa(MenuActions("/d", "/l"))
    assert BrowserView()._recreate_menus(["ours"]) == "menu bar"  # the error is logged, pywebview's bar stays
    assert calls == [["ours"]]
