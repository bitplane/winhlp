"""Tests for terminal paragraph-layout translation."""

from winhlp.lib.internal_files.topic import BorderInfo, ParagraphInfo, ParagraphInfoBits, Tab, TabInfo
from winhlp.lib.terminal_layout import expand_terminal_tabs, translate_paragraph


def _bits(**updates):
    values = {
        "unknown_follows": False,
        "spacing_above_follows": False,
        "spacing_below_follows": False,
        "spacing_lines_follows": False,
        "left_indent_follows": False,
        "right_indent_follows": False,
        "firstline_indent_follows": False,
        "unused": False,
        "borderinfo_follows": False,
        "tabinfo_follows": False,
        "right_aligned_paragraph": False,
        "center_aligned_paragraph": False,
    }
    values.update(updates)
    return ParagraphInfoBits(**values)


def test_translate_paragraph_preserves_indents_tabs_spacing_and_border_sides():
    paragraph = ParagraphInfo(
        topic_size=0,
        topic_length=0,
        bits=_bits(right_aligned_paragraph=True),
        left_indent=240,
        right_indent=120,
        firstline_indent=-120,
        spacing_above=48,
        spacing_below=24,
        spacing_lines=24,
        tab_info=TabInfo(
            number_of_tab_stops=2,
            tabs=[Tab(position=480, tab_type=0), Tab(position=1200, tab_type=1)],
        ),
        border_info=BorderInfo(
            border_box=False,
            border_top=True,
            border_left=False,
            border_bottom=True,
            border_right=False,
            border_thick=True,
            border_double=False,
            border_unknown=False,
            border_width=2,
        ),
        raw_data={},
    )

    layout = translate_paragraph(paragraph)

    assert (layout.left_indent, layout.right_indent, layout.first_line_indent) == (2, 1, -1)
    assert (layout.spacing_above, layout.spacing_below, layout.line_spacing) == (2, 1, 1)
    assert [tab.alignment for tab in layout.tabs] == ["left", "right"]
    assert layout.border.top and layout.border.bottom and not layout.border.left
    assert layout.border.thick


def test_expand_tabs_supports_right_and_decimal_alignment():
    paragraph = (Tab(position=1200, tab_type=1), Tab(position=2400, tab_type=3))
    tabs = TabInfo(number_of_tab_stops=2, tabs=list(paragraph))
    layout = translate_paragraph(ParagraphInfo(topic_size=0, topic_length=0, bits=_bits(), tab_info=tabs, raw_data={}))

    expanded = expand_terminal_tabs("item\t12\t3.5", layout.tabs)

    assert "\t" not in expanded
    assert expanded.index("12") < 10
    assert expanded.index(".") == 20
