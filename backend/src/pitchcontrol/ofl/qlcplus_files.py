"""The QLC+ fixture folders on this computer (item 54's "your QLC+ fixtures" list).

QLC+ keeps its fixture definitions in a ``Fixtures`` folder of its installation (thousands of ``.qxf`` files) and the
user's own ones in a second folder of the user's profile. The places per operating system are the ones OFL's QLC+
plugin lists (``fileLocations`` in ``plugins/qlcplus_4.12.2/plugin.json``), plus the QLC+ 5 and Program Files variants.
Only folders that exist are listed; the dialog offers the list when there is one.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import unescape

MAX_FILE_BYTES = 8_000_000  # the same limit as the reader (qlcplus.MAX_BYTES)
MAX_FIXTURES = 20_000
SUBFOLDERS = ("Fixtures", "fixtures")


@dataclass
class Folder:
    label: str  # "QLC+" or "your QLC+ fixtures"
    path: Path


def candidate_dirs(platform: str | None = None, env: dict[str, str] | None = None, home: Path | None = None) -> list[tuple[str, Path]]:
    """(label, installation or user folder) in the order they are looked at; the ``Fixtures`` folder is inside."""
    platform = platform or sys.platform
    env = os.environ if env is None else env
    home = home or Path.home()
    if platform.startswith("win"):
        program = [Path(env[k]) for k in ("ProgramFiles", "ProgramFiles(x86)") if env.get(k)]
        main = [Path("C:/QLC+"), Path("C:/QLC+5"), *(p / name for p in program for name in ("QLC+", "QLC+5"))]
        user = [home / "QLC+", home / "QLC+5"]
    elif platform == "darwin":
        main = [Path("/Applications/QLC+.app/Contents/Resources"), Path("/Applications/QLC+5.app/Contents/Resources")]
        user = [home / "Library" / "Application Support" / name for name in ("QLC+", "QLC+5")]
    else:
        main = [Path("/usr/share/qlcplus"), Path("/usr/local/share/qlcplus"), Path("/usr/share/qlcplus5")]
        user = [home / ".qlcplus", home / ".qlcplus5"]
    return [("QLC+", p) for p in main] + [("your QLC+ fixtures", p) for p in user]


def folders() -> list[Folder]:
    """The fixture folders that exist, without duplicates (a case-insensitive disk finds ``Fixtures`` and ``fixtures`` as one)."""
    found: list[Folder] = []
    seen: set[tuple] = set()
    for label, base in candidate_dirs():
        for sub in SUBFOLDERS:
            path = base / sub
            try:
                if not path.is_dir():
                    continue
                key = _identity(path)
            except OSError:
                continue
            if key in seen:
                continue
            seen.add(key)
            found.append(Folder(label, path))
    return found


def _identity(path: Path) -> tuple:
    """What makes two spellings of a folder the same folder: the disk's own id of it (device and inode), so that
    ``Fixtures`` and ``fixtures`` are one on macOS and Windows (``os.path.normcase`` only lowercases on Windows, so it
    listed the QLC+ folders twice on a Mac). Where the id is 0, the lower-cased real path."""
    st = path.stat()
    if st.st_ino:
        return ("id", st.st_dev, st.st_ino)
    return ("path", os.path.normcase(str(path.resolve())).lower())


def _tag(head: str, tag: str) -> str | None:
    match = re.search(rf"<{tag}>(.*?)</{tag}>", head, re.S)
    return unescape(match[1].strip(), {"&quot;": '"', "&apos;": "'"}) if match else None


def listing(places: list[Folder] | None = None) -> list[dict[str, str | int]]:
    """Every ``.qxf`` of the folders: ``folder`` (the index in ``folders()``), ``file``, ``manufacturer``, ``model``, ``type``.
    Only the top of each file is read (the three names come first), so thousands of files take a moment."""
    out: list[dict[str, str | int]] = []
    for index, folder in enumerate(places if places is not None else folders()):
        try:
            names = sorted(n for n in os.listdir(folder.path) if n.lower().endswith(".qxf"))
        except OSError:
            continue
        for name in names:
            if len(out) >= MAX_FIXTURES:
                return out
            try:
                with open(folder.path / name, "rb") as handle:
                    head = handle.read(4096).decode("utf-8", errors="replace")
            except OSError:
                continue
            stem = name[:-4]
            maker, model = _tag(head, "Manufacturer"), _tag(head, "Model")
            if not model:  # no readable header: the file name is "Manufacturer-Model.qxf"
                maker, _, model = stem.partition("-")
            out.append({"folder": index, "file": name, "manufacturer": maker or "", "model": model or stem, "type": _tag(head, "Type") or ""})
    return out


def read(places: list[Folder], folder: int, file: str) -> bytes:
    """The bytes of one listed file. Only a plain ``.qxf`` name inside one of the folders is read."""
    if not (0 <= folder < len(places)) or Path(file).name != file or not file.lower().endswith(".qxf"):
        raise FileNotFoundError("that is not a QLC+ fixture of this computer's QLC+ folders")
    path = places[folder].path / file
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"{file} is bigger than a fixture definition can be")
    return path.read_bytes()
