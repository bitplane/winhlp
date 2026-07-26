"""Interactive terminal viewer for parsed Windows Help files."""

from __future__ import annotations

import os
import locale
import re
import struct
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from rich import box
from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.padding import Padding
from rich.style import Style
from rich.table import Table as RichTable
from rich.text import Text
from textual import events, on
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import Button, Footer, Header, Input, Label, ListItem, ListView, Static, Tab, Tabs

from .lib.document import (
    HelpDocument,
    HelpNavigator,
    NavigationEntry,
    ResolvedTarget,
    help_title,
    parse_embedded_resource,
)
from .lib.hlp import HelpFile
from .lib.layout import layout_topic
from .lib.internal_files.topic import ParsedTopic, TextSpan, TopicTableBlock, TopicTextBlock
from .lib.raster import HalfBlockRasterizer, RasterHotspot, TerminalRasterizer, decode_bmp
from .lib.terminal_layout import translate_paragraph


WINHELP_THEME = Theme(
    name="winhelp",
    primary="#000080",
    secondary="#008080",
    warning="#808000",
    error="#800000",
    success="#008000",
    accent="#008000",
    foreground="#000000",
    background="#c0c0c0",
    surface="#ffffff",
    panel="#c0c0c0",
    boost="#000080",
    dark=False,
    luminosity_spread=0.12,
)


def _span_style(span: TextSpan) -> Style:
    """Preserve document emphasis while allowing the active theme to own colour."""
    return Style(
        italic=span.is_italic,
        underline=span.is_underline,
        underline2=span.is_double_underline,
        strike=span.is_strikethrough,
        bold=span.is_bold or bool(span.font_half_points and span.font_half_points >= 28),
        dim=bool(span.font_half_points and span.font_half_points <= 14),
    )


_SUPERSCRIPT = str.maketrans("0123456789+-=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾")
_SUBSCRIPT = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")


def _span_text(span: TextSpan) -> str:
    text = span.text.upper() if span.is_small_caps else span.text
    if span.is_superscript:
        return text.translate(_SUPERSCRIPT)
    if span.is_subscript:
        return text.translate(_SUBSCRIPT)
    return text


def _partial_border(text: Text, border) -> Text:
    """Render selected paragraph border sides without inventing missing sides."""
    vertical = "║" if border.double else "┃" if border.thick else "│"
    horizontal = "═" if border.double else "━" if border.thick else "─"
    lines = text.split("\n", allow_blank=True)
    width = max((line.cell_len for line in lines), default=1)
    output = Text()
    if border.top:
        output.append(horizontal * max(1, width + 2) + "\n")
    for index, line in enumerate(lines):
        output.append(vertical + " " if border.left else "")
        output.append_text(line)
        output.append(" " * max(0, width - line.cell_len))
        output.append(" " + vertical if border.right else "")
        if index + 1 < len(lines):
            output.append("\n")
    if border.bottom:
        output.append("\n" + horizontal * max(1, width + 2))
    return output


def _renderable_height(renderable: RenderableType) -> int:
    if isinstance(renderable, Text):
        return max(1, renderable.plain.count("\n") + 1)
    return 1


def _expand_styled_tabs(text: Text, tabs, default_size: int = 4) -> Text:
    """Expand tabs while retaining Rich spans, including click metadata."""
    if "\t" not in text.plain:
        return text
    plain = text.plain
    output: list[str] = []
    positions = [0] * (len(plain) + 1)
    column = 0
    output_length = 0
    for index, character in enumerate(plain):
        positions[index] = output_length
        if character == "\n":
            output.append(character)
            output_length += 1
            column = 0
            continue
        if character != "\t":
            output.append(character)
            output_length += 1
            column += 1
            continue
        following = plain[index + 1 :].split("\t", 1)[0].split("\n", 1)[0]
        stop = next((tab for tab in tabs if tab.column > column), None)
        if stop is None:
            target = ((column // default_size) + 1) * default_size
        elif stop.alignment == "right":
            target = stop.column - len(following)
        elif stop.alignment == "center":
            target = stop.column - len(following) // 2
        elif stop.alignment == "decimal":
            target = stop.column - (following.find(".") if "." in following else len(following))
        else:
            target = stop.column
        padding = max(1, target - column)
        output.append(" " * padding)
        output_length += padding
        column += padding
    positions[len(plain)] = output_length
    expanded = Text("".join(output), style=text.style)
    for span in text.spans:
        expanded.stylize(span.style, positions[span.start], positions[span.end])
    return expanded


def topic_label(topic: ParsedTopic, position: int) -> str:
    if topic.title:
        return topic.title
    if topic.topic_number is not None:
        return f"Topic {topic.topic_number}"
    return f"Topic {position + 1}"


class TopicView(Static):
    """A Rich-backed topic renderer with keyboard-selectable inline hotspots."""

    @property
    def link_style(self) -> Style:
        """Keep Textual's automatic link decoration away from raster pixels."""
        return Style.null()

    @property
    def link_style_hover(self) -> Style:
        """Use temporary reverse-video for hover while preserving the resting image."""
        return Style(reverse=True)

    can_focus = True

    def __init__(
        self,
        document: HelpDocument,
        topic: Optional[ParsedTopic] = None,
        *,
        interactive: bool = True,
        action_namespace: str = "app",
        start_block: int = 0,
        show_heading: bool = False,
        blocks: Optional[tuple] = None,
        target_base: int = 0,
        id: Optional[str] = None,
    ):
        super().__init__(id=id)
        self.document = document
        self.topic = topic
        self.interactive = interactive
        self.action_namespace = action_namespace
        self.start_block = start_block
        self.show_heading = show_heading
        self.blocks = blocks
        self.target_base = target_base
        self.targets: list[ResolvedTarget] = []
        self.target_lines: list[int] = []
        self.image_placeholders: list[str] = []
        self.rasterizer: TerminalRasterizer = HalfBlockRasterizer()
        self.selected_link = -1

    def on_mount(self) -> None:
        self.refresh_topic()

    def set_topic(self, topic: Optional[ParsedTopic]) -> None:
        self.topic = topic
        self.blocks = None
        self.selected_link = -1
        self.refresh_topic()

    def on_resize(self, _event=None) -> None:
        self.refresh_topic()

    def select_next_link(self, direction: int) -> bool:
        if not self.interactive or not self.targets:
            return False
        self.selected_link = (self.selected_link + direction) % len(self.targets)
        self.refresh_topic()
        self.focus()
        return True

    def selected_target(self) -> Optional[ResolvedTarget]:
        local = self.selected_link - self.target_base
        if 0 <= local < len(self.targets):
            return self.targets[local]
        return None

    def refresh_topic(self) -> None:
        self.targets = []
        self.target_lines = []
        self._current_line = 0
        self.image_placeholders = []
        renderables: list[RenderableType] = []
        if self.topic is None:
            renderables.append(Text("This help file contains no parsed topics.", style="italic dim"))
            self.update(Group(*renderables))
            return

        if self.show_heading:
            renderables.append(Text(self.topic.title or "Untitled topic", style="bold"))

        blocks = list(self.blocks) if self.blocks is not None else self.topic.content_blocks
        if not blocks:
            blocks = [TopicTextBlock(text_spans=self.topic.text_spans)]
            blocks.extend(TopicTableBlock(table=table) for table in self.topic.tables)
        for block in blocks[self.start_block :]:
            if isinstance(block, TopicTextBlock):
                rendered_block = list(self._render_text_block(block))
                renderables.extend(rendered_block)
                self._current_line += sum(_renderable_height(item) for item in rendered_block)
            else:
                renderables.append(self._render_table(block))
                self._current_line += max(1, len(block.table.rows))
        if self.topic.annotations:
            notes = Text()
            for annotation in self.topic.annotations:
                notes.append(f"• {annotation}\n")
            renderables.append(Panel(notes, title="Annotations"))
        self.update(Group(*renderables))

    def _render_text_block(self, block: TopicTextBlock) -> Iterable[RenderableType]:
        text = Text()
        mappings = {mapping.text_span_index: mapping for mapping in block.hotspot_mappings}
        last_image_marker = None

        def flush_text():
            nonlocal text
            if not text.plain:
                return None
            rendered = self._apply_paragraph_layout(text, block)
            text = Text()
            return rendered

        for index, span in enumerate(block.text_spans):
            start = len(text)
            text.append(_span_text(span), _span_style(span))
            end = len(text)
            target = None
            resource = parse_embedded_resource(span.embedded_image) if span.embedded_image else None
            if span.hyperlink_target:
                target = self.document.resolve_target(span.hyperlink_target)
            elif index in mappings:
                target = self.document.resolve_hotspot(mappings[index])
            elif resource is not None and resource.kind == "window" and resource.reference.startswith("!"):
                _label, separator, macro = resource.reference[1:].partition(",")
                if separator and macro:
                    target = self.document.resolve_target(f"macro:{macro}")
            if target is not None and self.interactive and end > start:
                link_index = self.target_base + len(self.targets)
                self.targets.append(target)
                self.target_lines.append(self._current_line + text.plain[:start].count("\n"))
                selected = link_index == self.selected_link
                style = Style(
                    underline=True,
                    reverse=selected,
                    meta={"@click": f"{self.action_namespace}.follow_link({link_index})"},
                )
                text.stylize(style, start, end)
            if span.embedded_image and span.embedded_image != last_image_marker:
                inline = (
                    self._render_inline_image(
                        resource,
                        target,
                        is_list_marker=(
                            index == 0
                            and index + 1 < len(block.text_spans)
                            and block.text_spans[index + 1].text.startswith("\t")
                        ),
                    )
                    if resource is not None and resource.alignment == "inline"
                    else None
                )
                if inline is not None:
                    text.append_text(inline)
                    last_image_marker = span.embedded_image
                    continue
                pending = flush_text()
                if pending is not None:
                    yield pending
                if resource is not None:
                    if resource.kind == "window" and resource.reference.startswith("!"):
                        if not span.text.strip() and target is not None:
                            yield self._render_object_button(target)
                    elif resource.kind == "window" and resource.reference.startswith("*"):
                        yield Text(f"[media: {resource.reference[1:]}]", style="italic dim")
                    else:
                        yield self._render_image(resource, target)
                last_image_marker = span.embedded_image
            elif not span.embedded_image:
                last_image_marker = None
        pending = flush_text()
        if pending is not None:
            yield pending

    def _apply_paragraph_layout(self, text: Text, block: TopicTextBlock) -> RenderableType:
        layout = translate_paragraph(block.paragraph_info)
        text = _expand_styled_tabs(text, layout.tabs)
        text.rstrip()
        list_match = re.match(r"^(?P<marker>\d+[.)]?|[▪•])\s+", text.plain)
        if list_match:
            marker = text[: list_match.end("marker")]
            body = text[list_match.end() :]
            item = RichTable.grid(expand=True, padding=(0, 1))
            item.add_column(no_wrap=True)
            item.add_column(ratio=1)
            item.add_row(marker, body)
            return item
        text.justify = layout.alignment
        lines = text.split("\n", allow_blank=True)
        rebuilt = Text()
        for index, line in enumerate(lines):
            indent = layout.left_indent + (layout.first_line_indent if index == 0 else 0)
            indent = max(0, min(24, indent))
            rebuilt.append(" " * indent)
            rebuilt.append_text(line)
            if layout.right_indent:
                rebuilt.append(" " * min(24, layout.right_indent))
            if index + 1 < len(lines):
                rebuilt.append("\n" * (1 + layout.line_spacing))
        text = rebuilt
        if layout.spacing_above:
            text = Text("\n" * layout.spacing_above) + text
        if layout.spacing_below:
            text.append("\n" * layout.spacing_below)
        border = layout.border
        if border:
            if all((border.top, border.right, border.bottom, border.left)):
                style = box.DOUBLE if border.double else box.HEAVY if border.thick else box.SQUARE
                return Panel(text, box=style, padding=(0, 1))
            text = _partial_border(text, border)
        return text

    def _render_object_button(self, target: ResolvedTarget) -> Text:
        link_index = self.target_base + len(self.targets)
        self.targets.append(target)
        self.target_lines.append(self._current_line)
        return Text(
            "▣",
            Style(
                underline=True,
                reverse=link_index == self.selected_link,
                meta={"@click": f"{self.action_namespace}.follow_link({link_index})"},
            ),
        )

    def _bitmap_resource(self, resource, target_width: int):
        label = resource.resource_name or resource.reference
        bitmaps = self.document.helpfile.bitmaps
        bitmap_file = bitmaps.get(label)
        if bitmap_file is None and label.startswith("|"):
            bitmap_file = bitmaps.get(label[1:])
        if bitmap_file is None and not label.startswith("|"):
            bitmap_file = bitmaps.get("|" + label)
        picture_index = bitmap_file.select_picture(target_width) if bitmap_file is not None else 0
        extracted = bitmap_file.extract_image(picture_index) if bitmap_file is not None else None
        image = decode_bmp(extracted[1]) if extracted and extracted[0] == "bmp" else None
        return label, bitmap_file, picture_index, extracted, image

    def _render_inline_image(
        self,
        resource,
        object_target: Optional[ResolvedTarget],
        *,
        is_list_marker: bool = False,
    ) -> Optional[Text]:
        """Render small inline icons in paragraph flow; leave larger art as blocks."""
        label, bitmap_file, picture_index, _extracted, image = self._bitmap_resource(resource, 16)
        if image is None or image.width > 32 or image.height > 32:
            return None
        source_hotspots = bitmap_file.bitmaps[picture_index].hotspots if bitmap_file is not None else []
        if source_hotspots:
            return None
        # WinHelp commonly uses a tiny embedded square as a list bullet. A
        # terminal bullet is clearer than expanding that bitmap to many rows.
        if object_target is None and is_list_marker and image.width <= 16 and image.height <= 16:
            return Text("▪")

        raster_hotspots = []
        selected = -1
        if object_target is not None:
            link_index = self.target_base + len(self.targets)
            self.targets.append(object_target)
            self.target_lines.append(self._current_line)
            raster_hotspots.append(
                RasterHotspot(
                    0,
                    0,
                    image.width,
                    image.height,
                    f"{self.action_namespace}.follow_link({link_index})",
                    reverse_on_select=False,
                )
            )
            if link_index == self.selected_link:
                selected = 0
        inline_width = max(1, min(4, round(image.width * 2 / max(image.height, 1))))
        return HalfBlockRasterizer(max_height=1).render(
            image,
            max_width=inline_width,
            hotspots=raster_hotspots,
            selected_hotspot=selected,
        )

    def _render_image(self, resource, object_target: Optional[ResolvedTarget] = None) -> RenderableType:
        target_width = max(8, (self.size.width or 64) - 2)
        label, bitmap_file, picture_index, extracted, image = self._bitmap_resource(resource, target_width)
        if image is None:
            reason = "missing resource" if extracted is None else f"unsupported {extracted[0].upper()}"
            placeholder = f"[image: {label}, {resource.alignment}; {reason}]"
            self.image_placeholders.append(placeholder)
            return Text(placeholder, style="italic dim")

        source_hotspots = bitmap_file.bitmaps[picture_index].hotspots if bitmap_file.bitmaps else []
        raster_hotspots = []
        labels = Text()
        selected_raster_hotspot = -1
        if object_target is not None:
            link_index = self.target_base + len(self.targets)
            self.targets.append(object_target)
            self.target_lines.append(self._current_line)
            action = f"{self.action_namespace}.follow_link({link_index})"
            # Reverse-video swaps the foreground/background halves of every
            # raster cell, visibly scrambling a whole linked image.
            raster_hotspots.append(
                RasterHotspot(
                    0,
                    0,
                    image.width,
                    image.height,
                    action,
                    reverse_on_select=False,
                )
            )
            if link_index == self.selected_link:
                selected_raster_hotspot = 0
        for hotspot_number, hotspot in enumerate(source_hotspots, start=1):
            target = self.document.resolve_bitmap_hotspot(hotspot)
            link_index = self.target_base + len(self.targets)
            self.targets.append(target)
            self.target_lines.append(self._current_line)
            if link_index == self.selected_link:
                selected_raster_hotspot = len(raster_hotspots)
            action = f"{self.action_namespace}.follow_link({link_index})"
            raster_hotspots.append(RasterHotspot(hotspot.x, hotspot.y, hotspot.width, hotspot.height, action))
            start = len(labels)
            accessible_label = hotspot.name or (target.topic.title if target.topic else target.original)
            labels.append(f"[{hotspot_number}] {accessible_label}\n")
            labels.stylize(
                Style(underline=True, reverse=link_index == self.selected_link, meta={"@click": action}),
                start,
                len(labels),
            )
        rendered = self.rasterizer.render(
            image,
            max_width=target_width,
            hotspots=raster_hotspots,
            selected_hotspot=selected_raster_hotspot,
        )
        output = Group(rendered, labels) if labels.plain else rendered
        if resource.alignment == "right":
            return Align.right(output)
        if resource.alignment == "left":
            return Align.left(output)
        return output

    def _render_table(self, block: TopicTableBlock) -> RichTable:
        parsed = block.table
        columns = max(parsed.column_count, max((len(row.cells) for row in parsed.rows), default=0), 1)
        table = RichTable(show_header=False, box=box.SIMPLE, pad_edge=False)
        widths = parsed.column_widths[:columns]
        width_total = sum(max(width, 1) for width in widths) or columns
        for column in range(columns):
            ratio = max(widths[column], 1) if column < len(widths) else max(1, width_total // columns)
            table.add_column(ratio=ratio)
        occupied = [0] * columns
        for row in parsed.rows:
            cells: list[RenderableType] = []
            source_index = 0
            column = 0
            while column < columns:
                if occupied[column] > 0:
                    occupied[column] -= 1
                    cells.append(Text())
                    column += 1
                    continue
                if source_index >= len(row.cells):
                    cells.append(Text())
                    column += 1
                    continue
                cell = row.cells[source_index]
                source_index += 1
                rendered = self._render_table_cell(cell)
                if row.height and row.height >= 120:
                    rendered = Padding(rendered, (0, 0, min(4, row.height // 120 - 1), 0))
                cells.append(rendered)
                span = max(1, min(cell.column_span, columns - column))
                if cell.row_span > 1:
                    for span_column in range(column, column + span):
                        occupied[span_column] = max(occupied[span_column], cell.row_span - 1)
                cells.extend(Text() for _ in range(span - 1))
                column += span
            table.add_row(*cells[:columns])
        return table

    def _render_table_cell(self, cell) -> RenderableType:
        parts: list[RenderableType] = []
        text = Text()
        for span in cell.text_spans:
            if span.embedded_image:
                if text.plain:
                    parts.append(text)
                    text = Text()
                resource = parse_embedded_resource(span.embedded_image)
                if resource is not None:
                    target = self.document.resolve_target(span.hyperlink_target) if span.hyperlink_target else None
                    parts.append(self._render_image(resource, target))
                continue
            start = len(text)
            text.append(_span_text(span), _span_style(span))
            if span.hyperlink_target:
                target = self.document.resolve_target(span.hyperlink_target)
                link_index = self.target_base + len(self.targets)
                self.targets.append(target)
                self.target_lines.append(self._current_line)
                text.stylize(
                    Style(
                        underline=True,
                        reverse=link_index == self.selected_link,
                        meta={"@click": f"{self.action_namespace}.follow_link({link_index})"},
                    ),
                    start,
                    len(text),
                )
        text.justify = cell.alignment
        if text.plain or not parts:
            parts.append(text)
        rendered: RenderableType = Group(*parts) if len(parts) > 1 else parts[0]
        border = translate_paragraph(cell.paragraph_info).border
        if border is None and cell.border_info is not None:
            synthetic = cell.border_info
            if any(
                (
                    synthetic.border_box,
                    synthetic.border_top,
                    synthetic.border_right,
                    synthetic.border_bottom,
                    synthetic.border_left,
                )
            ):
                style = box.DOUBLE if synthetic.border_double else box.HEAVY if synthetic.border_thick else box.SQUARE
                rendered = Panel(rendered, box=style, padding=0)
        elif border:
            rendered = Panel(rendered, box=box.DOUBLE if border.double else box.SQUARE, padding=0)
        return rendered


class TopicPopup(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("tab", "next_link", "Next link", priority=True),
        Binding("shift+tab", "previous_link", "Previous link", priority=True),
        Binding("enter", "activate_link", "Open link", priority=True),
        Binding("b,alt+left", "history_back", "Back"),
        Binding("f,alt+right", "history_forward", "Forward"),
    ]

    def __init__(self, document: HelpDocument, topic: ParsedTopic):
        super().__init__()
        self.document = document
        self.topic = topic
        self.back_stack: list[ParsedTopic] = []
        self.forward_stack: list[ParsedTopic] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="popup"):
            if self.title:
                yield Label(str(self.title), classes="popup-title")
            yield VerticalScroll(
                TopicView(self.document, self.topic, interactive=True, action_namespace="screen", id="popup-topic")
            )
            yield Label("Esc: close", id="popup-hint")

    def action_dismiss(self) -> None:
        self.dismiss()

    def action_follow_link(self, index: int) -> None:
        view = self.query_one("#popup-topic", TopicView)
        if 0 <= index < len(view.targets):
            self._activate(view.targets[index])

    def action_next_link(self) -> None:
        self.query_one("#popup-topic", TopicView).select_next_link(1)

    def action_previous_link(self) -> None:
        self.query_one("#popup-topic", TopicView).select_next_link(-1)

    def action_activate_link(self) -> None:
        target = self.query_one("#popup-topic", TopicView).selected_target()
        if target is not None:
            self._activate(target)

    def _activate(self, target: ResolvedTarget) -> None:
        if target.topic is not None and target.kind in ("topic", "popup"):
            if target.topic is not self.topic:
                self.back_stack.append(self.topic)
                self.forward_stack.clear()
            self.topic = target.topic
            self.query_one("#popup-topic", TopicView).set_topic(target.topic)
        elif target.kind == "choice" and target.topics:
            self.app.push_screen(TopicChoicePopup("Choose a topic", target.topics), self._topic_chosen)
        elif target.kind == "external":
            self.dismiss()
            self.app._activate_external_target(target)
        else:
            self.app.push_screen(DiagnosticPopup(target.detail or f"Unsupported target: {target.original}"))

    def _topic_chosen(self, topic: Optional[ParsedTopic]) -> None:
        if topic is not None:
            self._activate(ResolvedTarget("topic", "choice", topic=topic, document=self.document))

    def action_history_back(self) -> None:
        if self.back_stack:
            self.forward_stack.append(self.topic)
            self.topic = self.back_stack.pop()
            self.query_one("#popup-topic", TopicView).set_topic(self.topic)

    def action_history_forward(self) -> None:
        if self.forward_stack:
            self.back_stack.append(self.topic)
            self.topic = self.forward_stack.pop()
            self.query_one("#popup-topic", TopicView).set_topic(self.topic)


class DiagnosticPopup(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", "Close"), Binding("q", "dismiss", "Close")]

    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="diagnostic"):
            yield Static(self.message)
            yield Label("Esc: close", id="popup-hint")

    def action_dismiss(self) -> None:
        self.dismiss()


class InformationPopup(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", "Close"), Binding("q", "dismiss", "Close")]

    def __init__(self, title: str, content: RenderableType):
        super().__init__()
        self.popup_title = title
        self.content = content

    def compose(self) -> ComposeResult:
        with Vertical(id="popup"):
            yield Label(self.popup_title, classes="popup-title")
            yield VerticalScroll(Static(self.content))
            yield Label("Esc: close", id="popup-hint")

    def action_dismiss(self) -> None:
        self.dismiss()


class TopicChoiceList(ListView):
    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            event.stop()
            self.screen.action_choose()


class TopicChoicePopup(ModalScreen):
    """Choose one of several topics associated with an index keyword."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("enter", "choose", "Open", priority=True),
    ]

    def __init__(self, label: str, topics: tuple[ParsedTopic, ...]):
        super().__init__()
        self.label = label
        self.topics = topics

    def compose(self) -> ComposeResult:
        with Vertical(id="popup"):
            yield Label(self.label, classes="popup-title")
            yield TopicChoiceList(
                *(ListItem(Label(topic.title or f"Topic {topic.topic_number}")) for topic in self.topics),
                id="topic-choices",
            )
            yield Label("Enter: open · Esc: close", id="popup-hint")

    def on_mount(self) -> None:
        choices = self.query_one("#topic-choices", ListView)
        choices.index = 0
        choices.focus()

    @on(ListView.Selected, "#topic-choices")
    def topic_selected(self, event: ListView.Selected) -> None:
        if event.list_view.index is not None:
            self.dismiss(self.topics[event.list_view.index])

    def action_dismiss(self) -> None:
        self.dismiss(None)

    def action_choose(self) -> None:
        index = self.query_one("#topic-choices", ListView).index
        if index is not None:
            self.dismiss(self.topics[index])


class HelpTopicsScreen(ModalScreen[Optional[NavigationEntry]]):
    """Windows Help-style Contents and keyword Index browser."""

    INDEX_BROWSE_LIMIT = 400

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("enter", "choose", "Display", priority=True),
    ]

    def __init__(self, document: HelpDocument, initial: str = "contents"):
        super().__init__()
        self.document = document
        self.mode = initial if initial in ("contents", "index") else "contents"
        self.all_entries: list[NavigationEntry] = []
        self.entries: list[NavigationEntry] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="help-topics"):
            yield Label(f"Help Topics: {help_title(self.document.helpfile)}", classes="popup-title")
            yield Tabs(
                Tab("Contents", id="contents"),
                Tab("Index", id="index"),
                active=self.mode,
                id="help-tabs",
            )
            yield Label("", id="help-instructions")
            yield Input(placeholder="Type the first few letters of the word…", id="help-index-search")
            yield ListView(id="help-entries")
            yield Label("Enter: display · Esc: close", id="popup-hint")

    def on_mount(self) -> None:
        self._set_mode(self.mode)

    @on(Tabs.TabActivated, "#help-tabs")
    def tab_activated(self, event: Tabs.TabActivated) -> None:
        if event.tab.id:
            self._set_mode(event.tab.id)

    def _set_mode(self, mode: str) -> None:
        self.mode = mode
        search = self.query_one("#help-index-search", Input)
        instructions = self.query_one("#help-instructions", Label)
        if mode == "index":
            self.all_entries = self.document.index_entries()
            search.display = True
            suffix = (
                f" Showing the first {self.INDEX_BROWSE_LIMIT} until you type."
                if len(self.all_entries) > self.INDEX_BROWSE_LIMIT
                else ""
            )
            instructions.update("Type the first few letters, then choose an index entry." + suffix)
            self._filter_index(search.value)
            search.focus()
        else:
            self.all_entries = self.document.contents_entries()
            search.display = False
            instructions.update("Choose a book or topic, then press Enter.")
            self.entries = list(self.all_entries)
            self.run_worker(self._replace_entries(), group="help-entries", exclusive=True)

    def _entry_item(self, entry: NavigationEntry) -> ListItem:
        if self.mode == "contents":
            icon = "▰" if entry.kind in ("book", "heading") or (entry.topic is None and entry.level == 0) else "◇"
        else:
            icon = " "
        return ListItem(Label(f"{'  ' * entry.level}{icon} {entry.label}"))

    async def _replace_entries(self) -> None:
        view = self.query_one("#help-entries", ListView)
        await view.clear()
        if self.entries:
            await view.extend(self._entry_item(entry) for entry in self.entries)
            view.index = 0
        if self.mode == "contents":
            view.focus()

    def _filter_index(self, query: str) -> None:
        folded = query.casefold().strip()
        if not folded:
            self.entries = list(self.all_entries[: self.INDEX_BROWSE_LIMIT])
        else:
            starts = [
                entry for entry in self.all_entries if (entry.target or entry.label).casefold().startswith(folded)
            ]
            self.entries = (
                starts or [entry for entry in self.all_entries if folded in (entry.target or entry.label).casefold()]
            )[: self.INDEX_BROWSE_LIMIT]
        self.run_worker(self._replace_entries(), group="help-entries", exclusive=True)

    @on(Input.Changed, "#help-index-search")
    def index_changed(self, event: Input.Changed) -> None:
        if self.mode == "index":
            self._filter_index(event.value)

    @on(Input.Submitted, "#help-index-search")
    def index_submitted(self) -> None:
        self.action_choose()

    @on(ListView.Selected, "#help-entries")
    def entry_selected(self) -> None:
        self.action_choose()

    def action_choose(self) -> None:
        index = self.query_one("#help-entries", ListView).index
        if index is None or index >= len(self.entries):
            return
        entry = self.entries[index]
        if entry.kind in ("book", "heading") and entry.topic is None and not entry.topics and not entry.macro:
            return
        self.dismiss(entry)

    def action_dismiss(self) -> None:
        self.dismiss(None)


class OptionsScreen(ModalScreen[Optional[str]]):
    """Compact menu for less-frequent WinHelp viewer actions."""

    OPTIONS = (
        ("topic_details", "Topic Details"),
        ("file_information", "Help File Information"),
        ("parse_errors", "Parser Diagnostics"),
        ("change_theme", "Change Theme"),
    )
    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("enter", "choose", "Open", priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="options-menu"):
            yield Label("Options", classes="popup-title")
            yield ListView(
                *(ListItem(Label(label)) for _action, label in self.OPTIONS),
                id="option-entries",
            )
            yield Label("Enter: open · Esc: close", id="popup-hint")

    def on_mount(self) -> None:
        options = self.query_one("#option-entries", ListView)
        options.index = 0
        options.focus()

    @on(ListView.Selected, "#option-entries")
    def option_selected(self) -> None:
        self.action_choose()

    def action_choose(self) -> None:
        index = self.query_one("#option-entries", ListView).index
        if index is not None:
            self.dismiss(self.OPTIONS[index][0])

    def action_dismiss(self) -> None:
        self.dismiss(None)


class WinHlpApp(App):
    """Browse a parsed Windows Help file in the terminal."""

    CSS = """
    Screen { layout: vertical; background: $background; color: $text; }
    #toolbar { height: 3; background: $panel; }
    #toolbar Button { height: 3; min-width: 0; margin: 0; }
    #toolbar-help { width: 13; }
    #toolbar-back { width: 7; }
    #toolbar-options { width: 9; }
    #body { height: 1fr; }
    #sidebar { display: none; width: 30; border-right: solid $primary; background: $panel; }
    #search { dock: top; }
    #topics { height: 1fr; }
    #topic-pane { width: 1fr; background: $surface; }
    #topic-scroll { width: 1fr; padding: 1 2; background: $surface; }
    #fixed-header {
        display: none;
        height: auto;
        max-height: 12;
        padding: 1 2;
        border-bottom: solid $primary;
        background: $surface;
        color: $text;
    }
    #topic-view, #fixed-header { width: 1fr; height: auto; background: $surface; color: $text; }
    TopicPopup, DiagnosticPopup, HelpTopicsScreen, OptionsScreen {
        align: center middle;
        background: $background 70%;
    }
    #popup, #diagnostic { width: 80%; height: 80%; padding: 1 2; border: heavy $accent; background: $surface; }
    #help-topics { width: 82%; height: 86%; padding: 1 2; border: heavy $primary; background: $panel; }
    #help-tabs { height: 3; }
    #help-instructions { height: 2; padding: 0 1; }
    #help-index-search { height: 3; }
    #help-entries { height: 1fr; background: $surface; }
    #options-menu {
        width: 42;
        max-width: 94%;
        height: 15;
        padding: 1 2;
        border: heavy $primary;
        background: $panel;
    }
    #option-entries { height: 1fr; background: $surface; }
    #diagnostic { height: auto; max-height: 16; }
    #popup-hint { dock: bottom; height: 1; color: $text-muted; }
    .popup-title { height: 2; text-style: bold; color: $primary; }
    #sidebar-title { height: 1; text-style: bold; padding-left: 1; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("b,alt+left", "history_back", "Back", show=False),
        Binding("f,alt+right", "history_forward", "Forward", show=False),
        Binding("[", "browse_previous", "Browse prev"),
        Binding("]", "browse_next", "Browse next"),
        Binding("/", "focus_search", "Search"),
        Binding("t", "toggle_sidebar", "Topics"),
        Binding("o", "show_topics", "Help Topics", show=False),
        Binding("c", "show_contents", "Contents", show=False),
        Binding("k", "show_index", "Index", show=False),
        Binding("i", "file_information", "File info", show=False),
        Binding("d", "topic_details", "Topic details", show=False),
        Binding("e", "parse_errors", "Errors", show=False),
        Binding("tab", "next_link", "Next link", priority=True),
        Binding("shift+tab", "previous_link", "Previous link", priority=True),
        Binding("enter", "activate_link", "Open link"),
    ]

    def __init__(self, helpfile, *, show_help_topics_on_start: bool = True):
        super().__init__()
        self.register_theme(WINHELP_THEME)
        self.theme = WINHELP_THEME.name
        self.helpfile = helpfile
        self.show_help_topics_on_start = show_help_topics_on_start
        self.document = helpfile.get_document()
        self.navigator = HelpNavigator(self.document)
        self.document_back_stack: list[tuple[HelpFile, HelpDocument, HelpNavigator]] = []
        self.document_forward_stack: list[tuple[HelpFile, HelpDocument, HelpNavigator]] = []
        self.sidebar_mode = "topics"
        self.visible_topics = list(self.document.topics)
        self.sidebar_entries = [
            NavigationEntry(topic_label(topic, index), topic) for index, topic in enumerate(self.document.topics)
        ]
        self.title = help_title(helpfile)
        self.sub_title = os.path.basename(helpfile.filepath)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="toolbar"):
            yield Button("Help Topics", id="toolbar-help", compact=True)
            yield Button("Back", id="toolbar-back", compact=True, disabled=True)
            yield Button("Options", id="toolbar-options", compact=True)
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Label("Topics", id="sidebar-title")
                yield Input(placeholder="Search topics…", id="search")
                yield ListView(*self._topic_items(self.sidebar_entries), id="topics")
            with Vertical(id="topic-pane"):
                yield TopicView(self.document, self.navigator.current, id="fixed-header")
                with VerticalScroll(id="topic-scroll"):
                    yield TopicView(self.document, self.navigator.current, id="topic-view")
        yield Footer()

    def on_mount(self) -> None:
        self._update_subtitle()
        self._show_current()
        self.query_one("#topic-view", TopicView).focus()
        if self.show_help_topics_on_start:
            self.call_after_refresh(self._show_help_topics, "contents")

    def get_system_commands(self, screen):
        yield from super().get_system_commands(screen)
        yield SystemCommand(
            "Help Topics",
            "Browse this help file's Contents and Index",
            self.action_show_topics,
        )

    @on(Button.Pressed, "#toolbar-help")
    def toolbar_help_pressed(self) -> None:
        self.action_show_topics()

    @on(Button.Pressed, "#toolbar-back")
    def toolbar_back_pressed(self) -> None:
        self.action_history_back()

    @on(Button.Pressed, "#toolbar-options")
    def toolbar_options_pressed(self) -> None:
        self.action_show_options()

    @staticmethod
    def _topic_items(entries) -> list[ListItem]:
        return [ListItem(Label("  " * entry.level + entry.label)) for entry in entries]

    def _show_current(self) -> None:
        topic = self.navigator.current
        layout = layout_topic(topic) if topic is not None else None
        fixed = self.query_one("#fixed-header", TopicView)
        fixed.document = self.document
        fixed.target_base = 0
        fixed.show_heading = False
        fixed.display = bool(layout and layout.fixed_blocks)
        fixed.set_topic(topic if fixed.display else None)
        fixed.blocks = layout.fixed_blocks if layout else ()
        fixed.refresh_topic()
        view = self.query_one("#topic-view", TopicView)
        view.document = self.document
        view.target_base = len(fixed.targets)
        view.show_heading = False
        view.set_topic(topic)
        view.blocks = layout.scrolling_blocks if layout else ()
        view.refresh_topic()
        self.query_one("#topic-scroll", VerticalScroll).scroll_home(animate=False)
        self._update_subtitle()
        self._update_toolbar_state()

    def _update_toolbar_state(self) -> None:
        buttons = list(self.query("#toolbar-back"))
        if buttons:
            buttons[0].disabled = not bool(self.navigator.back_stack or self.document_back_stack)

    def _update_subtitle(self) -> None:
        current = self.navigator.current
        if current is None:
            self.sub_title = os.path.basename(self.helpfile.filepath)
            return
        position = self.document.topics.index(current) + 1
        warning = f" · ⚠ {len(self.helpfile.parse_errors)}" if self.helpfile.parse_errors else ""
        self.sub_title = f"{os.path.basename(self.helpfile.filepath)} · {position}/{len(self.document.topics)}{warning}"

    def action_follow_link(self, index: int) -> None:
        targets = self._all_targets()
        if 0 <= index < len(targets):
            self._activate_target(targets[index])

    def _all_targets(self) -> list[ResolvedTarget]:
        return [
            *self.query_one("#fixed-header", TopicView).targets,
            *self.query_one("#topic-view", TopicView).targets,
        ]

    def _activate_target(self, target: ResolvedTarget) -> None:
        if target.kind == "topic" and target.topic is not None:
            self.navigator.go_to(target.topic)
            self._show_current()
        elif target.kind == "popup" and target.topic is not None:
            self.push_screen(TopicPopup(self.document, target.topic))
        elif target.kind == "choice" and target.topics:
            self.push_screen(TopicChoicePopup("Choose a topic", target.topics), self._topic_chosen)
        elif target.kind == "external":
            self._activate_external_target(target)
        else:
            self.push_screen(DiagnosticPopup(target.detail or f"Unsupported target: {target.original}"))

    def _activate_external_target(self, target: ResolvedTarget) -> None:
        source_document = target.document if isinstance(target.document, HelpDocument) else self.document
        source_helpfile = source_document.helpfile
        fields = {}
        for field in target.original.split("|"):
            key, separator, value = field.partition(":")
            if separator:
                fields[key] = value
        try:
            offset = int(fields["topic_offset"], 0)
        except (KeyError, ValueError):
            offset = None

        filename = fields.get("file")
        if not filename:
            topic = (
                source_document.topic_by_context_name(fields["context_name"])
                if fields.get("context_name")
                else source_document.topic_for_offset(offset)
            )
            if topic is not None:
                fields = self._with_viola_window(source_helpfile, topic, fields)
                if target.open_as_popup or "window" in fields or "window_number" in fields:
                    popup = TopicPopup(source_document, topic)
                    popup.title = self._window_caption(source_helpfile, fields)
                    self.push_screen(popup)
                else:
                    if source_document is self.document:
                        self.navigator.go_to(topic)
                        self._show_current()
                    else:
                        self.document_back_stack.append((self.helpfile, self.document, self.navigator))
                        self.document_forward_stack.clear()
                        self._switch_document(source_helpfile, source_document, HelpNavigator(source_document, topic))
                return
            self.push_screen(DiagnosticPopup(target.detail or f"Could not resolve target: {target.original}"))
            return

        candidate = self._sibling_help_path(filename, source_helpfile)
        if candidate is None:
            self.push_screen(DiagnosticPopup(f"Sibling help file was not found: {filename}"))
            return
        try:
            helpfile = HelpFile(filepath=str(candidate))
            document = helpfile.get_document()
        except Exception as error:
            self.push_screen(DiagnosticPopup(f"Could not open {candidate.name}: {error}"))
            return
        topic = (
            document.topic_by_context_name(fields["context_name"])
            if fields.get("context_name")
            else document.topic_for_offset(offset)
            if offset is not None
            else document.initial_topic
        )
        if topic is None:
            self.push_screen(DiagnosticPopup(f"{candidate.name} does not contain the requested topic."))
            return
        fields = self._with_viola_window(helpfile, topic, fields)
        if target.open_as_popup or "window" in fields or "window_number" in fields:
            popup = TopicPopup(document, topic)
            popup.title = self._window_caption(helpfile, fields)
            self.push_screen(popup)
            return
        self.document_back_stack.append((self.helpfile, self.document, self.navigator))
        self.document_forward_stack.clear()
        self._switch_document(helpfile, document, HelpNavigator(document, topic))

    def _sibling_help_path(self, filename: str, source_helpfile: Optional[HelpFile] = None) -> Optional[Path]:
        """Find a named sibling HLP without allowing the target to escape its directory."""
        requested = Path(filename.replace("\\", "/")).name
        directory = Path((source_helpfile or self.helpfile).filepath).resolve().parent
        exact = directory / requested
        if exact.is_file():
            return exact
        folded = requested.casefold()
        try:
            return next(path for path in directory.iterdir() if path.is_file() and path.name.casefold() == folded)
        except (OSError, StopIteration):
            return None

    @staticmethod
    def _window_caption(helpfile: HelpFile, fields: dict[str, str]) -> str:
        system = helpfile.system
        records = [
            record.get("window_info")
            for record in (system.records if system else [])
            if isinstance(record, dict) and record.get("type") == "WINDOW"
        ]
        requested_name = fields.get("window")
        requested_number = fields.get("window_number")
        for index, info in enumerate(info for info in records if info):
            if (requested_name and info.get("name", "").casefold() == requested_name.casefold()) or (
                requested_number is not None and str(index) == requested_number
            ):
                return info.get("caption") or info.get("name") or "Secondary Help Window"
        return "Secondary Help Window"

    @staticmethod
    def _with_viola_window(helpfile: HelpFile, topic: ParsedTopic, fields: dict[str, str]) -> dict[str, str]:
        if "window" in fields or "window_number" in fields or helpfile.viola is None:
            return fields
        for entry in helpfile.viola.entries:
            if entry.topic_offset == topic.topic_offset:
                return {**fields, "window_number": str(entry.window_number)}
        return fields

    def _switch_document(self, helpfile: HelpFile, document: HelpDocument, navigator: HelpNavigator) -> None:
        self.helpfile = helpfile
        self.document = document
        self.navigator = navigator
        self.title = help_title(helpfile)
        self.sidebar_entries = self._filter_sidebar_entries("")
        self.visible_topics = [entry.topic for entry in self.sidebar_entries if entry.topic is not None]
        self.run_worker(self._replace_sidebar_items(), group="document-sidebar", exclusive=True)
        self._show_current()

    async def _replace_sidebar_items(self) -> None:
        topics = self.query_one("#topics", ListView)
        await topics.clear()
        if self.sidebar_entries:
            await topics.extend(self._topic_items(self.sidebar_entries))

    def action_next_link(self) -> None:
        if self.focused is self.query_one("#search", Input):
            self.query_one("#topics", ListView).focus()
            return
        self._select_link(1)

    def action_previous_link(self) -> None:
        self._select_link(-1)

    def _select_link(self, direction: int) -> None:
        targets = self._all_targets()
        if not targets:
            return
        fixed = self.query_one("#fixed-header", TopicView)
        scrolling = self.query_one("#topic-view", TopicView)
        current = max(fixed.selected_link, scrolling.selected_link)
        selected = (current + direction) % len(targets) if current >= 0 else (0 if direction > 0 else len(targets) - 1)
        fixed.selected_link = selected
        scrolling.selected_link = selected
        fixed.refresh_topic()
        scrolling.refresh_topic()
        (fixed if selected < len(fixed.targets) else scrolling).focus()
        if selected >= len(fixed.targets):
            local = selected - len(fixed.targets)
            if local < len(scrolling.target_lines):
                self.query_one("#topic-scroll", VerticalScroll).scroll_to(
                    y=max(0, scrolling.target_lines[local] - 2), animate=False
                )

    def action_activate_link(self) -> None:
        if self.focused is self.query_one("#search", Input):
            if self.visible_topics:
                self.navigator.go_to(self.visible_topics[0])
                self._show_current()
                self.query_one("#topic-view", TopicView).focus()
            return
        fixed = self.query_one("#fixed-header", TopicView)
        scrolling = self.query_one("#topic-view", TopicView)
        target = fixed.selected_target() or scrolling.selected_target()
        if target is not None:
            self._activate_target(target)

    def action_history_back(self) -> None:
        current = self.navigator.current
        self.navigator.back()
        if self.navigator.current is not current:
            self._show_current()
        elif self.document_back_stack:
            previous = self.document_back_stack.pop()
            self.document_forward_stack.append((self.helpfile, self.document, self.navigator))
            self._switch_document(*previous)

    def action_history_forward(self) -> None:
        current = self.navigator.current
        self.navigator.forward()
        if self.navigator.current is not current:
            self._show_current()
        elif self.document_forward_stack:
            following = self.document_forward_stack.pop()
            self.document_back_stack.append((self.helpfile, self.document, self.navigator))
            self._switch_document(*following)

    def action_browse_previous(self) -> None:
        current = self.navigator.current
        self.navigator.browse_previous()
        if self.navigator.current is not current:
            self._show_current()

    def action_browse_next(self) -> None:
        current = self.navigator.current
        self.navigator.browse_next()
        if self.navigator.current is not current:
            self._show_current()

    def action_focus_search(self) -> None:
        self.query_one("#sidebar").display = True
        self.query_one("#search", Input).focus()

    def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar")
        sidebar.display = not sidebar.display

    def action_show_topics(self) -> None:
        self._show_help_topics("contents")

    def action_show_contents(self) -> None:
        self._show_help_topics("contents")

    def action_show_index(self) -> None:
        self._show_help_topics("index")

    def action_show_options(self) -> None:
        self.push_screen(OptionsScreen(), self._option_chosen)

    def _option_chosen(self, action: Optional[str]) -> None:
        if action == "topic_details":
            self.action_topic_details()
        elif action == "file_information":
            self.action_file_information()
        elif action == "parse_errors":
            self.action_parse_errors()
        elif action == "change_theme":
            self.action_change_theme()

    def _show_help_topics(self, initial: str) -> None:
        self.push_screen(HelpTopicsScreen(self.document, initial), self._help_entry_chosen)

    def _help_entry_chosen(self, entry: Optional[NavigationEntry]) -> None:
        if entry is not None:
            self._activate_navigation_entry(entry)

    async def _set_sidebar_mode(self, mode: str) -> None:
        self.sidebar_mode = mode
        self.query_one("#sidebar-title", Label).update(mode.title())
        search = self.query_one("#search", Input)
        search.placeholder = f"Search {mode}…"
        self.sidebar_entries = self._filter_sidebar_entries(search.value)
        self.visible_topics = [entry.topic for entry in self.sidebar_entries if entry.topic is not None]
        topics = self.query_one("#topics", ListView)
        await topics.clear()
        if self.sidebar_entries:
            await topics.extend(self._topic_items(self.sidebar_entries))
        topics.focus()

    def _filter_sidebar_entries(self, query: str):
        folded = query.casefold().strip()
        if self.sidebar_mode == "topics":
            topics = self.document.search(query)
            positions = {id(topic): index for index, topic in enumerate(self.document.topics)}
            return [NavigationEntry(topic_label(topic, positions[id(topic)]), topic) for topic in topics]
        entries = self.document.contents_entries() if self.sidebar_mode == "contents" else self.document.index_entries()
        return [entry for entry in entries if not folded or folded in entry.label.casefold()]

    def action_file_information(self) -> None:
        system = self.helpfile.system
        header = self.helpfile.header
        lines = [
            f"File: {self.helpfile.filepath}",
            f"File size: {len(self.helpfile.data):,} bytes",
            f"Title: {help_title(self.helpfile)}",
            f"Topics: {len(self.document.topics)}",
            f"Format: {_format_version(system)}",
            f"Encoding: {system.encoding}" if system else "Encoding: unknown",
            f"Locale: {_format_locale(system)}",
            f"Charset: {_format_charset(system)}",
            f"Compression: {_format_compression(system)}",
            f"Generated: {_format_generation_date(system)}",
            f"Copyright: {system.copyright}" if system and system.copyright else "",
            f"Container size: {header.entire_file_size:,}" if header else "",
            f"Directory offset: {header.directory_start:#x}" if header else "",
            f"Free-chain offset: {header.free_chain_start:#x}" if header else "",
            f"Internal files: {len(self.helpfile.directory.files) if self.helpfile.directory else 0}",
            f"Parsed with warnings: {len(self.helpfile.parse_errors)}",
        ]
        if system:
            citation = next(
                (
                    record.get("citation_text")
                    for record in system.records
                    if isinstance(record, dict) and record.get("type") == "CITATION"
                ),
                None,
            )
            lines.extend(
                line
                for line in (
                    f"Citation: {citation}" if citation else "",
                    f"CNT file: {system.cnt_filename}" if system.cnt_filename else "",
                    f"Icon: {len(system.icon):,} bytes" if system.icon else "",
                    f"Default font: {_system_record_summary(system, 'DEFFONT')}",
                    f"DLL mappings: {len(system.dllmaps)}" if system.dllmaps else "",
                    f"Groups: {len(system.groups)}" if system.groups else "",
                )
                if line
            )
            window_records = [
                record for record in system.records if isinstance(record, dict) and record.get("type") == "WINDOW"
            ]
            lines.append(f"Window definitions: {len(window_records)}")
            for index, record in enumerate(window_records):
                info = record.get("window_info", {})
                lines.append(
                    f"  [{index}] {info.get('name') or '(unnamed)'}: "
                    f"{info.get('caption') or '(no caption)'} ({info.get('window_type', 'unknown')})"
                )
        if self.helpfile.gmacros:
            lines.append("\nGlobal macros:")
            for macro in self.helpfile.gmacros.entries:
                lines.append(f"  enter: {macro.entry_macro}")
                lines.append(f"  exit:  {macro.exit_macro}")
        for config_number in sorted(self.helpfile.config_files):
            macros = self.helpfile.get_config_macros(config_number)
            if macros:
                lines.append(f"\nConfiguration {config_number} macros:")
                lines.extend(f"  {macro}" for macro in macros)
        definitions = self.helpfile.get_all_macro_definitions()
        if definitions:
            lines.append("\nIndexed macro definitions:")
            lines.extend(f"  {macro} [{title}]" for _, macro, title in definitions)
        if self.helpfile.directory and self.helpfile.directory.files:
            lines.append("\nInternal files:")
            for name, offset in sorted(self.helpfile.directory.files.items()):
                status = "parsed"
                if any(error.get("file") == name for error in self.helpfile.parse_errors):
                    status = "warning"
                try:
                    _reserved, used, _flags = struct.unpack_from("<llB", self.helpfile.data, offset)
                    size = f"{used:,} bytes"
                except struct.error:
                    size = "truncated"
                lines.append(f"  {name}: {size} [{status}]")
        if self.helpfile.is_gid_file:
            lines.append("\nGID diagnostics:")
            lines.append(
                f"  WinPos: {'parsed' if self.helpfile.winpos and self.helpfile.winpos.btree else 'unavailable'}"
            )
            lines.append(
                f"  CntJump entries: {len(self.helpfile.cntjump.jump_references) if self.helpfile.cntjump else 0}"
            )
            lines.append(
                f"  CntText entries: {len(self.helpfile.cnttext.topic_titles) if self.helpfile.cnttext else 0}"
            )
            lines.append(f"  Pete bytes: {len(self.helpfile.pete.raw_data) if self.helpfile.pete else 0}")
            lines.append(f"  Flags bytes: {len(self.helpfile.flags.raw_data) if self.helpfile.flags else 0}")
        if self.helpfile.parse_errors:
            lines.append("\nInternal-file diagnostics:")
            lines.extend(
                f"  {error.get('file', 'unknown')}: {error.get('error', error)}" for error in self.helpfile.parse_errors
            )
        self.push_screen(InformationPopup("Help File Information", Text("\n".join(line for line in lines if line))))

    def action_topic_details(self) -> None:
        topic = self.navigator.current
        if topic is None:
            return
        links = []
        resources = []
        unresolved = []
        for block in topic.content_blocks:
            spans = (
                block.text_spans
                if isinstance(block, TopicTextBlock)
                else [span for row in block.table.rows for cell in row.cells for span in cell.text_spans]
            )
            for span in spans:
                if span.hyperlink_target:
                    links.append(span.hyperlink_target)
                    resolved = self.document.resolve_target(span.hyperlink_target)
                    if resolved.kind == "unresolved":
                        unresolved.append(span.hyperlink_target)
                if span.embedded_image:
                    resources.append(span.embedded_image)
        for mapping in topic.hotspot_mappings:
            links.append(mapping.target)
            if self.document.resolve_hotspot(mapping).kind == "unresolved":
                unresolved.append(mapping.target)
        petra_source = self.helpfile.petra.get_rtf_filename(topic.topic_offset) if self.helpfile.petra else None
        groups = [
            f"{name}:{group.get_group_for_topic(topic.topic_number)}"
            for name, group in self.helpfile.grp_files.items()
            if topic.topic_number is not None and group.get_group_for_topic(topic.topic_number) is not None
        ]
        viola = [
            entry.window_number
            for entry in (self.helpfile.viola.entries if self.helpfile.viola else [])
            if entry.topic_offset == topic.topic_offset
        ]
        browse_previous = self.document.browse_previous(topic)
        browse_next = self.document.browse_next(topic)
        lines = [
            f"Title: {topic.title or '(untitled)'}",
            f"Topic number: {topic.topic_number}",
            f"Topic offset: {topic.topic_offset}",
            f"Non-scrolling offset: {topic.non_scroll_offset}",
            "Context IDs: " + (", ".join(topic.context_names) or "(none)"),
            "Keywords: " + (", ".join(topic.keywords) or "(none)"),
            "Entry macros: " + (", ".join(topic.entry_macros) or "(none)"),
            f"Browse previous: {browse_previous.title if browse_previous else '(none)'}",
            f"Browse next: {browse_next.title if browse_next else '(none)'}",
            f"Source RTF: {petra_source or '(unknown)'}",
            f"Groups: {', '.join(groups) or '(none)'}",
            f"Window assignments: {', '.join(map(str, viola)) or '(none)'}",
            f"Blocks: {len(topic.content_blocks)} ({len(topic.tables)} tables)",
            "Links: " + (", ".join(dict.fromkeys(links)) or "(none)"),
            "Embedded resources: " + (", ".join(dict.fromkeys(resources)) or "(none)"),
            "Unresolved targets: " + (", ".join(dict.fromkeys(unresolved)) or "(none)"),
            f"Annotations ({len(topic.annotations)}):",
            *(f"  {annotation}" for annotation in topic.annotations),
        ]
        if resources:
            lines.append("Resource details:")
            for marker in dict.fromkeys(resources):
                resource = parse_embedded_resource(marker)
                bitmap = self.helpfile.bitmaps.get(resource.resource_name) if resource else None
                if bitmap is None and resource:
                    bitmap = self.helpfile.bitmaps.get("|" + resource.resource_name.lstrip("|"))
                lines.append(
                    f"  {marker}: "
                    f"{len(bitmap.bitmaps) if bitmap else 0} picture(s), "
                    f"{sum(len(picture.hotspots) for picture in bitmap.bitmaps) if bitmap else 0} hotspot(s)"
                )
        local_errors = [
            error
            for error in self.helpfile.parse_errors
            if str(topic.topic_offset) in str(error) or (topic.title and topic.title in str(error))
        ]
        if local_errors:
            lines.append("Local diagnostics:")
            lines.extend(f"  {error.get('file', 'unknown')}: {error.get('error', error)}" for error in local_errors)
        self.push_screen(InformationPopup("Topic Details", Text("\n".join(lines))))

    def action_parse_errors(self) -> None:
        errors = self.helpfile.parse_errors
        if not errors:
            content = Text("No nonfatal parser errors were recorded.")
        else:
            content = Text(
                "\n\n".join(f"{error.get('file', 'unknown')}: {error.get('error', error)}" for error in errors)
            )
        self.push_screen(InformationPopup("Parser Diagnostics", content))

    @on(Input.Changed, "#search")
    async def search_changed(self, event: Input.Changed) -> None:
        self.sidebar_entries = self._filter_sidebar_entries(event.value)
        self.visible_topics = [entry.topic for entry in self.sidebar_entries if entry.topic is not None]
        topics = self.query_one("#topics", ListView)
        await topics.clear()
        if self.sidebar_entries:
            await topics.extend(self._topic_items(self.sidebar_entries))

    @on(Input.Submitted, "#search")
    def search_submitted(self) -> None:
        if self.visible_topics:
            self.navigator.go_to(self.visible_topics[0])
            self._show_current()
            self.query_one("#topic-view", TopicView).focus()

    @on(ListView.Selected, "#topics")
    def topic_selected(self, event: ListView.Selected) -> None:
        if event.list_view.index is None or event.list_view.index >= len(self.sidebar_entries):
            return
        self._activate_navigation_entry(self.sidebar_entries[event.list_view.index])

    def _activate_navigation_entry(self, entry: NavigationEntry) -> None:
        if len(entry.topics) > 1:
            self.push_screen(TopicChoicePopup(entry.label, entry.topics), self._topic_chosen)
            return
        if entry.macro:
            self._activate_target(self.document.resolve_target(f"macro:{entry.macro}"))
            return
        topic = entry.topic or (entry.topics[0] if entry.topics else None)
        if topic is None:
            if entry.kind == "unresolved":
                self.push_screen(DiagnosticPopup(f"Could not resolve Help target: {entry.target or entry.label}"))
            return
        self.navigator.go_to(topic)
        self._show_current()
        self.query_one("#topic-view", TopicView).focus()

    def _topic_chosen(self, topic: Optional[ParsedTopic]) -> None:
        if topic is not None:
            self.navigator.go_to(topic)
            self._show_current()
            self.query_one("#topic-view", TopicView).focus()


def run_tui(helpfile) -> None:
    """Run the terminal viewer for a parsed HelpFile."""
    WinHlpApp(helpfile).run()


def _format_version(system) -> str:
    if not system or not system.header:
        return "unknown"
    minor = system.header.minor
    family = (
        "WinHelp 3.0"
        if minor <= 16
        else "WinHelp 3.1"
        if minor <= 21
        else "Multimedia Viewer"
        if minor == 27
        else "WinHelp 4.0"
        if minor >= 33
        else "WinHelp"
    )
    return f"{family} ({system.header.major}.{minor})"


def _format_locale(system) -> str:
    if not system or system.lcid is None:
        return "unavailable"
    name = locale.windows_locale.get(system.lcid, "unknown locale")
    return f"{name} ({system.lcid:#06x})"


def _format_charset(system) -> str:
    if not system or system.charset is None:
        return "unavailable"
    names = {
        0: "ANSI",
        1: "Default",
        2: "Symbol",
        77: "Mac",
        128: "Shift-JIS",
        129: "Hangul",
        134: "GB2312",
        136: "Big5",
        161: "Greek",
        162: "Turkish",
        177: "Hebrew",
        178: "Arabic",
        186: "Baltic",
        204: "Cyrillic",
        222: "Thai",
        238: "Eastern European",
    }
    return f"{names.get(system.charset, 'unknown')} ({system.charset})"


def _format_compression(system) -> str:
    if not system or not system.header:
        return "unknown"
    flags = system.header.flags
    names = {0: "uncompressed, 4 KiB topic blocks", 4: "LZ77, 4 KiB topic blocks", 8: "LZ77, 2 KiB topic blocks"}
    return f"{names.get(flags, 'unknown')} (flags {flags:#06x})"


def _format_generation_date(system) -> str:
    if not system or not system.header or not system.header.gen_date:
        return "unavailable"
    try:
        return datetime.fromtimestamp(system.header.gen_date).isoformat(sep=" ")
    except (OverflowError, ValueError):
        return f"invalid ({system.header.gen_date})"


def _system_record_summary(system, record_type: str) -> str:
    for record in system.records:
        if isinstance(record, dict) and record.get("type") == record_type:
            parsed = record.get("raw_data", {}).get("parsed", {})
            return ", ".join(f"{key}={value}" for key, value in parsed.items()) or "present"
    return "unavailable"
