"""The desktop app's menu bar: one definition for both platforms (item 52).

macOS shows it as the native menu bar (pywebview's ``menu=``, see ``native_menu``); Windows draws it in the UI's
header row, from ``GET /api/menu`` (pywebview's native Windows strip is light, unstyled and shows no keys).

Every item has one action, whichever menu runs it:

- ``ui``: the page does it (switch page, Save, full screen, the Edit commands on Windows). The drawn menu calls the
  page's ``runMenu`` directly; the native menu asks the window to (``window.pitchMenu(id)`` through ``evaluate_js``).
- ``app``: Python does it (``MenuActions.run``): open a folder or a link, minimize, zoom, quit through the quit guard.
  The drawn menu asks through ``POST /api/menu/{id}`` (this computer only), the native menu calls it directly.
- ``native``: the operating system's own command: Cut, Copy, Paste and Select All on macOS (``cut:`` … with ⌘X …,
  which is what keeps ⌘C / ⌘V / ⌘A working in text fields), and Quit (⌘Q).

pywebview's menu items take no keyboard shortcuts (its ``menu.py`` has a TODO), so ``arrange_cocoa_menu`` adds the
macOS key equivalents itself and puts the menus in the usual order.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

log = logging.getLogger(__name__)

DOCS_URL = "https://pitchcontrol.eu/docs"
DISCORD_URL = "https://discord.gg/4nbBaQDKz4"

# the page tabs, in the order of the keys 1 to 9, then 0 (App.tsx: PAGES)
PAGES = ["General", "Dimmers", "Fixtures", "Rig", "Inputs", "Outputs", "Fog", "Settings", "Control Desk", "Help"]


@dataclass(frozen=True)
class Item:
    id: str
    label: str
    kind: str  # "ui", "app" or "native" (see the module doc)
    win_key: str = ""  # shown next to the item in the Windows menu
    mac_key: str = ""  # the macOS key equivalent: "cmd+s", "ctrl+cmd+f"
    only: str = ""  # "mac" or "win": the item exists on that platform only


@dataclass(frozen=True)
class Submenu:
    """An item that opens a menu of its own (File → Import Fixture ▸); one level deep."""

    label: str
    items: tuple[Item | None, ...]
    only: str = ""


SEPARATOR = None

# (title, items)
MENUS: list[tuple[str, list[Item | Submenu | None]]] = [
    (
        "PitchControl",  # macOS: the application menu (pywebview adds Services, Hide and Quit ⌘Q)
        [
            Item("app.about", "About PitchControl", "ui", only="mac"),
            Item("app.settings", "Settings…", "ui", mac_key="cmd+,", only="mac"),
        ],
    ),
    (
        "File",
        [
            Item("file.save", "Save", "ui", win_key="Ctrl+S", mac_key="cmd+s"),
            SEPARATOR,
            Submenu("Import Fixture", (Item("file.import.ofl", "Open Fixture Library…", "ui"),)),
            SEPARATOR,
            Item("file.data_folder", "Open data folder", "app"),
            Item("file.logs_folder", "Open logs folder", "app"),
            SEPARATOR,
            Item("file.quit", "Quit", "app", win_key="Alt+F4", only="win"),  # macOS: the application menu's Quit ⌘Q
        ],
    ),
    (
        "Edit",
        [
            Item("edit.cut", "Cut", "native", win_key="Ctrl+X", mac_key="cmd+x"),
            Item("edit.copy", "Copy", "native", win_key="Ctrl+C", mac_key="cmd+c"),
            Item("edit.paste", "Paste", "native", win_key="Ctrl+V", mac_key="cmd+v"),
            SEPARATOR,
            Item("edit.select_all", "Select All", "native", win_key="Ctrl+A", mac_key="cmd+a"),
        ],
    ),
    (
        "View",
        [
            # Help is 0: ⌘0 stays the UI scale's 100 %, so on macOS it has no key equivalent (the plain 0 works)
            *(Item(f"view.page.{n % 10}", page, "ui", win_key=str(n % 10), mac_key=f"cmd+{n}" if n < 10 else "") for n, page in enumerate(PAGES, 1)),
            SEPARATOR,
            Item("view.fullscreen", "Full screen", "ui", win_key="F", mac_key="ctrl+cmd+f"),
        ],
    ),
    (
        "Window",
        [
            Item("window.minimize", "Minimize", "app", mac_key="cmd+m"),
            Item("window.zoom", "Zoom", "app", only="mac"),
            Item("window.maximize", "Maximize", "app", only="win"),
        ],
    ),
    (
        "Help",
        [
            Item("help.docs", "Documentation", "app"),
            Item("help.keys", "Keyboard shortcuts", "ui"),
            SEPARATOR,
            Item("help.report", "Report a problem", "ui"),
            Item("help.discord", "Join the Discord", "app"),
            SEPARATOR,
            Item("app.about", "About PitchControl", "ui", only="win"),
        ],
    ),
]


def platform_of(sys_platform: str = sys.platform) -> str:
    return "mac" if sys_platform == "darwin" else "win"


def _kept(items, platform: str) -> list:
    """``items`` for one platform: the other platform's left out, no separator at either end or twice in a row, a
    submenu left empty dropped."""
    kept: list = []
    for item in items:
        if item is SEPARATOR:
            if kept and kept[-1] is not SEPARATOR:
                kept.append(SEPARATOR)
        elif item.only and item.only != platform:
            continue
        elif isinstance(item, Submenu):
            sub = _kept(item.items, platform)
            if sub:
                kept.append(Submenu(item.label, tuple(sub)))
        else:
            kept.append(item)
    while kept and kept[-1] is SEPARATOR:
        kept.pop()
    return kept


def menus_for(platform: str) -> list[tuple[str, list[Item | Submenu | None]]]:
    """The menus of one platform ("mac" or "win"): the items of the other platform left out, no separator at either
    end of a menu or twice in a row, and menus left empty dropped (the application menu on Windows)."""
    return [(title, kept) for title, items in MENUS if (kept := _kept(items, platform))]


def walk(items) -> Iterator[Item]:
    """Every item of a list, the ones inside submenus too."""
    for item in items:
        if isinstance(item, Submenu):
            yield from walk(item.items)
        elif item is not SEPARATOR:
            yield item


def items_by_id() -> dict[str, Item]:
    return {item.id: item for _, items in MENUS for item in walk(items)}


def _entry_json(item: Item | Submenu | None, platform: str) -> dict | None:
    if item is SEPARATOR:
        return None
    if isinstance(item, Submenu):
        return {"submenu": item.label, "items": [_entry_json(i, platform) for i in item.items]}
    return {"id": item.id, "label": item.label, "kind": item.kind, "key": item.win_key if platform == "win" else ""}


def menu_json(platform: str) -> list[dict]:
    """``GET /api/menu``: the menus the UI draws (Windows)."""
    return [{"title": title, "items": [_entry_json(i, platform) for i in items]} for title, items in menus_for(platform)]


def reveal(folder: str) -> None:
    """Show a folder in Finder / Explorer (made first if it doesn't exist yet)."""
    Path(folder).mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(folder)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", folder])


class MenuActions:
    """The ``app`` actions, and the way to the page for the ``ui`` ones. ``window`` is the pywebview window (None in
    tests and without a window); ``opener`` and ``revealer`` are replaceable for the tests."""

    def __init__(
        self,
        data_dir: str,
        logs_dir: str,
        window=None,
        opener: Callable[[str], object] = webbrowser.open,
        revealer: Callable[[str], None] = reveal,
    ) -> None:
        self.data_dir = data_dir
        self.logs_dir = logs_dir
        self.window = window
        self.opener = opener
        self.revealer = revealer
        self.zoomed = False  # Windows: maximized (kept from the window's events)

    def run(self, item_id: str) -> None:
        """Run one item. Raises KeyError for an unknown id and ValueError for an item the page or the system runs."""
        item = items_by_id()[item_id]
        if item.kind == "ui":
            self.to_page(item_id)
            return
        if item.kind != "app":
            raise ValueError(f"{item_id} is the system's own command")
        log.info("menu: %s", item_id)
        if item_id == "file.data_folder":
            self.revealer(self.data_dir)
        elif item_id == "file.logs_folder":
            self.revealer(self.logs_dir)
        elif item_id == "help.docs":
            self.opener(DOCS_URL)
        elif item_id == "help.discord":
            self.opener(DISCORD_URL)
        elif self.window is None:
            log.warning("menu: %s needs the window", item_id)
        elif item_id == "file.quit":
            # closing the window runs the quit guard (desktop.py: on_closing); in a thread of its own, because the
            # guard's dialog waits for an answer and quitting stops the server this request may have come through
            threading.Thread(target=self.window.destroy, name="menu-quit", daemon=True).start()
        elif item_id == "window.minimize":
            self.window.minimize()
        elif item_id == "window.zoom":
            self._zoom_mac()
        elif item_id == "window.maximize":
            (self.window.restore if self.zoomed else self.window.maximize)()

    def to_page(self, item_id: str) -> None:
        """A ``ui`` item from the native menu: the page runs it (``runMenu`` in App.tsx)."""
        if self.window is None:
            return
        self.window.evaluate_js(f"window.pitchMenu && window.pitchMenu({item_id!r})")

    def _zoom_mac(self) -> None:
        from PyObjCTools import AppHelper

        def zoom() -> None:
            ns = self.window.native
            if ns is not None:
                ns.zoom_(None)

        AppHelper.callAfter(zoom)


def native_menu(actions: MenuActions) -> list:
    """The macOS menu bar for ``webview.start(menu=…)``. The Edit menu is pywebview's own (native ``cut:`` … with
    ⌘X …); ``arrange_cocoa_menu`` puts it after File and adds the key equivalents."""
    from webview.menu import Menu, MenuAction, MenuSeparator

    def action(item: Item) -> Callable[[], None]:
        def run() -> None:
            try:
                actions.run(item.id)
            except Exception:  # noqa: BLE001
                log.exception("menu: %s failed", item.id)

        run.__name__ = item.id.replace(".", "_")  # pywebview names the registered action after the function
        return run

    def entries(items) -> list:
        return [
            MenuSeparator() if i is SEPARATOR else Menu(i.label, entries(i.items)) if isinstance(i, Submenu) else MenuAction(i.label, action(i))
            for i in items
        ]

    menus = []
    for title, items in menus_for("mac"):
        if title == "Edit":
            continue  # pywebview's own, native
        menus.append(Menu("__app__" if title == "PitchControl" else title, entries(items)))
    return menus


# AppKit modifier flags (kept numeric so this module imports without AppKit)
_MODIFIERS = {"cmd": 1 << 20, "ctrl": 1 << 18, "alt": 1 << 19, "shift": 1 << 17}


def key_equivalent(spec: str) -> tuple[str, int]:
    """``"ctrl+cmd+f"`` → (``"f"``, the modifier mask)."""
    *mods, key = spec.split("+")
    mask = 0
    for m in mods:
        mask |= _MODIFIERS[m]
    return key, mask


def selector(sel) -> str:
    """A menu item's action as text (PyObjC hands a selector over as bytes or str; None when there is none)."""
    return sel.decode() if isinstance(sel, bytes) else str(sel or "")


def arrange_cocoa_menu(main_menu, about: Callable[[], None] | None = None) -> None:
    """Called with each menu bar pywebview builds (``patch_cocoa``), on the main thread: drop pywebview's default View
    menu (its native full screen is not the app's), put its Edit menu after File, give the items their key
    equivalents, and let About show the app's own About (Help → About, with the full version)."""
    def submenus():
        for index in range(main_menu.numberOfItems()):
            entry = main_menu.itemAtIndex_(index)
            if entry.submenu() is not None:
                yield entry, entry.submenu()

    for entry, sub in list(submenus()):
        if sub.title() == "View" and any(selector(sub.itemAtIndex_(i).action()) == "toggleFullScreen:" for i in range(sub.numberOfItems())):
            main_menu.removeItem_(entry)
    titles = [sub.title() for _, sub in submenus()]
    edit = next((entry for entry, sub in submenus() if sub.title() == "Edit"), None)
    if edit is not None and "File" in titles:
        main_menu.removeItem_(edit)
        main_menu.insertItem_atIndex_(edit, [sub.title() for _, sub in submenus()].index("File") + 1)

    keys = {(title if title != "PitchControl" else "__app__", i.label): i.mac_key for title, items in menus_for("mac") for i in items if isinstance(i, Item) and i.mac_key}
    for index, (entry, sub) in enumerate(submenus()):
        title = "__app__" if index == 0 else sub.title()
        for i in range(sub.numberOfItems()):
            ns_item = sub.itemAtIndex_(i)
            spec = keys.get((title, ns_item.title()))
            if spec and title != "Edit":  # the Edit menu has its keys already
                key, mask = key_equivalent(spec)
                ns_item.setKeyEquivalent_(key)
                ns_item.setKeyEquivalentModifierMask_(mask)
            if index == 0 and about is not None and selector(ns_item.action()) == "orderFrontStandardAboutPanel:":
                from webview.platforms.cocoa import menu_handler

                menu_handler.register_action("app_about.pitchcontrol", about)
                ns_item.setTitle_("About PitchControl")
                ns_item.setTarget_(menu_handler)
                ns_item.setAction_("handleMenuAction:")
                ns_item.setRepresentedObject_("app_about.pitchcontrol")


def patch_cocoa(actions: MenuActions) -> None:
    """Have pywebview's macOS menu builder hand each menu bar to ``arrange_cocoa_menu``. If that fails, pywebview's
    own layout stays (App, Edit, View, File, View, …): untidy, but every item, and ⌘C / ⌘V, still works."""
    try:
        from webview.platforms.cocoa import BrowserView

        original = BrowserView._recreate_menus

        def recreate(self, user_menu):
            main_menu = original(self, user_menu)
            try:
                arrange_cocoa_menu(main_menu, about=lambda: actions.run("app.about"))
            except Exception:  # noqa: BLE001
                log.exception("arranging the macOS menu bar failed: pywebview's layout stays")
            return main_menu

        BrowserView._recreate_menus = recreate
    except Exception:  # noqa: BLE001
        log.exception("can't arrange the macOS menu bar: pywebview's layout stays")
