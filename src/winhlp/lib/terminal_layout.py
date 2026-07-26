"""Terminal-oriented, toolkit-neutral paragraph layout translation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .internal_files.topic import ParagraphInfo


@dataclass(frozen=True)
class TerminalTab:
    column: int
    alignment: str = "left"


@dataclass(frozen=True)
class TerminalBorder:
    top: bool
    right: bool
    bottom: bool
    left: bool
    thick: bool
    double: bool
    width: int


@dataclass(frozen=True)
class TerminalParagraphLayout:
    alignment: str = "left"
    left_indent: int = 0
    right_indent: int = 0
    first_line_indent: int = 0
    spacing_above: int = 0
    spacing_below: int = 0
    line_spacing: int = 0
    tabs: tuple[TerminalTab, ...] = ()
    border: Optional[TerminalBorder] = None


def translate_paragraph(paragraph: Optional[ParagraphInfo]) -> TerminalParagraphLayout:
    if paragraph is None:
        return TerminalParagraphLayout()
    alignment = (
        "center"
        if paragraph.bits.center_aligned_paragraph
        else "right"
        if paragraph.bits.right_aligned_paragraph
        else "left"
    )
    tab_names = {0: "left", 1: "right", 2: "center", 3: "decimal"}
    tabs = tuple(
        TerminalTab(max(1, tab.position // 120), tab_names.get(tab.tab_type & 3, "left"))
        for tab in (paragraph.tab_info.tabs if paragraph.tab_info else ())
    )
    source = paragraph.border_info
    border = (
        TerminalBorder(
            source.border_top or source.border_box,
            source.border_right or source.border_box,
            source.border_bottom or source.border_box,
            source.border_left or source.border_box,
            source.border_thick,
            source.border_double,
            source.border_width,
        )
        if source
        and any((source.border_box, source.border_top, source.border_right, source.border_bottom, source.border_left))
        else None
    )
    return TerminalParagraphLayout(
        alignment,
        max(0, (paragraph.left_indent or 0) // 120),
        max(0, (paragraph.right_indent or 0) // 120),
        int((paragraph.firstline_indent or 0) // 120),
        max(0, (paragraph.spacing_above or 0) // 24),
        max(0, (paragraph.spacing_below or 0) // 24),
        max(0, (paragraph.spacing_lines or 0) // 24),
        tabs,
        border,
    )


def expand_terminal_tabs(text: str, tabs: tuple[TerminalTab, ...]) -> str:
    """Expand tabs using left/right/centre/decimal stops with safe degradation."""
    if "\t" not in text:
        return text
    output = []
    column = 0
    pieces = text.split("\t")
    output.append(pieces[0])
    column = len(pieces[0].rsplit("\n", 1)[-1])
    for piece in pieces[1:]:
        stop = next((tab for tab in tabs if tab.column > column), None)
        if stop is None:
            target = ((column // 8) + 1) * 8
        elif stop.alignment == "right":
            target = stop.column - len(piece.split("\t", 1)[0])
        elif stop.alignment == "center":
            target = stop.column - len(piece.split("\t", 1)[0]) // 2
        elif stop.alignment == "decimal":
            target = stop.column - (piece.find(".") if "." in piece else len(piece))
        else:
            target = stop.column
        padding = max(1, target - column)
        output.append(" " * padding + piece)
        column += padding + len(piece)
    return "".join(output)
