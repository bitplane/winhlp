"""Safe parser for the line-oriented WinHelp Contents (.CNT) format."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CntEntry:
    label: str
    level: int
    reference: str = ""
    kind: str = "topic"
    base_file: str = ""


@dataclass(frozen=True)
class CntIndex:
    label: str
    target: str
    base_file: str = ""


@dataclass(frozen=True)
class CntDocument:
    title: str = ""
    base_file: str = ""
    entries: tuple[CntEntry, ...] = ()
    indices: tuple[CntIndex, ...] = ()
    diagnostics: tuple[str, ...] = ()


def load_cnt(path: Path, encoding: str = "cp1252") -> CntDocument:
    """Read a CNT and recursively combine safe sibling includes."""
    return _load_cnt(path.resolve(), encoding, ())


def _load_cnt(path: Path, encoding: str, stack: tuple[Path, ...]) -> CntDocument:
    if path in stack:
        chain = " -> ".join(item.name for item in (*stack, path))
        return CntDocument(diagnostics=(f"include cycle: {chain}",))
    try:
        raw = path.read_bytes()
    except OSError as error:
        return CntDocument(diagnostics=(f"{path.name}: {error}",))
    text = raw.decode(encoding, errors="replace")
    title = ""
    base_file = ""
    entries = []
    indices: list[CntIndex] = []
    diagnostics = []
    for number, original in enumerate(text.splitlines(), start=1):
        line = original.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith(":"):
            command, _, value = line[1:].partition(" ")
            command = command.casefold()
            value = value.strip()
            if command == "title":
                title = value
            elif command == "base":
                base_file = Path(value.replace("\\", "/")).name
            elif command == "index":
                label, separator, target = value.partition("=")
                indices.append(CntIndex(label.strip(), target.strip() if separator else "", base_file))
            elif command == "include":
                requested = value.strip().strip("\"`'").replace("\\", "/")
                if not requested or Path(requested).name != requested:
                    diagnostics.append(f"line {number}: CNT include is not a sibling file: {value}")
                    continue
                included = _load_cnt(path.parent / requested, encoding, (*stack, path))
                entries.extend(included.entries)
                indices.extend(included.indices)
                diagnostics.extend(f"{requested}: {message}" for message in included.diagnostics)
            continue
        level_text, separator, body = line.partition(" ")
        if not separator or not level_text.isdigit():
            diagnostics.append(f"line {number}: unrecognized CNT entry")
            continue
        label, has_target, reference = body.strip().partition("=")
        entries.append(
            CntEntry(
                label.strip(),
                max(0, int(level_text) - 1),
                reference.strip() if has_target else "",
                "topic" if has_target else "book",
                base_file,
            )
        )
    return CntDocument(title, base_file, tuple(entries), tuple(indices), tuple(diagnostics))
