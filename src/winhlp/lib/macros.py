"""Strictly allowlisted interpretation of navigation-only WinHelp macros."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class NavigationMacro:
    name: str
    arguments: tuple[str, ...]


_NAVIGATION_MACROS = {
    "alink": "alink",
    "al": "alink",
    "klink": "klink",
    "kl": "klink",
    "jumpid": "jumpid",
    "ji": "jumpid",
    "jumpcontext": "jumpcontext",
    "jc": "jumpcontext",
    "jumphash": "jumphash",
    "jh": "jumphash",
    "popupid": "popupid",
    "pi": "popupid",
    "popupcontext": "popupcontext",
    "pc": "popupcontext",
    "popuphash": "popuphash",
}


def _parse_arguments(source: str) -> tuple[str, ...] | None:
    """Split macro arguments while honoring WinHelp's three quote styles."""
    arguments = []
    current = []
    quote = None
    escaped = False
    for character in source:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif quote:
            if character == quote:
                quote = None
            else:
                current.append(character)
        elif character in ('"', "'", "`"):
            quote = character
        elif character == ",":
            arguments.append("".join(current).strip())
            current = []
        elif character in "()":
            # Nested expressions are intentionally outside this safe subset.
            return None
        else:
            current.append(character)
    if quote or escaped:
        return None
    arguments.append("".join(current).strip())
    return tuple(arguments) if arguments != [""] else ()


def parse_navigation_macro(source: str) -> NavigationMacro | None:
    """Parse only known, side-effect-free navigation macro forms."""
    match = re.fullmatch(r"\s*([A-Za-z][A-Za-z0-9]*)\s*\((.*)\)\s*", source, re.DOTALL)
    if not match:
        return None
    name = _NAVIGATION_MACROS.get(match.group(1).casefold())
    if name is None:
        return None
    arguments = _parse_arguments(match.group(2))
    return NavigationMacro(name, arguments) if arguments is not None else None
