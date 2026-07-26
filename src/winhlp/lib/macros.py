"""Strictly allowlisted interpretation of navigation-only WinHelp macros."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class NavigationMacro:
    name: str
    arguments: tuple[str, ...]


_NAVIGATION_MACROS = {"jumpid", "jumpcontext", "popupid", "alink", "klink"}


def parse_navigation_macro(source: str) -> NavigationMacro | None:
    """Parse only known, side-effect-free navigation macro forms."""
    match = re.fullmatch(r"\s*([A-Za-z][A-Za-z0-9]*)\s*\((.*)\)\s*", source, re.DOTALL)
    if not match or match.group(1).casefold() not in _NAVIGATION_MACROS:
        return None
    try:
        arguments = next(csv.reader([match.group(2)], skipinitialspace=True))
    except (csv.Error, StopIteration):
        return None
    return NavigationMacro(match.group(1).casefold(), tuple(argument.strip() for argument in arguments))
