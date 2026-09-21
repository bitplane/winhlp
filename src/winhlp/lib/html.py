"""Render a parsed HelpFile to a single self-contained HTML document.

The whole help file becomes one HTML page: a table of contents followed by every
topic as an anchored ``<section>``. Internal jumps/popups resolve to in-page
``#anchor`` links (via each topic's TOPICOFFSET), character formatting comes from
the |FONT descriptors as CSS classes, and images are either embedded as data
URIs (self-contained) or written to a folder and referenced by ``<img src>``.
"""

import base64
import html
import io
import os
import re
from typing import Optional
from urllib.parse import quote

from PIL import Image

from .document import parse_embedded_resource
from .internal_files.topic import TopicTableBlock, TopicTextBlock
from .layout import layout_topic
from .raster import load_wmf


def _to_png(data: bytes, ext: str, size: Optional[tuple[int, int]] = None) -> tuple:
    """Convert a decoded bitmap or metafile to PNG.

    PNG is smaller (our BMPs are uncompressed) and renders everywhere; if Pillow
    can't decode the image we keep the original bytes. Returns (bytes, ext).
    """
    if ext not in ("bmp", "wmf"):
        return data, ext
    try:
        img = load_wmf(data, size) if ext == "wmf" else Image.open(io.BytesIO(data))
        if img is None:
            return data, ext
        with img:
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return buf.getvalue(), "png"
    except Exception:  # pragma: no cover - malformed image
        return data, ext


# embedded_image markers:
#   "bitmap:<align>:<number>"   -> |bmN / bmN resource
#   "window:<align>:<ewc str>"  -> MediaView embedded window "DLL, Class, Param"
# align is bmc (inline text char), bml (float left), bmr (float right).
_IMG_STYLE = {"left": ' style="float:left;margin:0 1em 0.5em 0"', "right": ' style="float:right;margin:0 0 0.5em 1em"'}


class HtmlExporter:
    def __init__(self, helpfile, images: str = "embed", image_dir: Optional[str] = None):
        """images: "embed" (data URIs) or "extract" (write files to image_dir)."""
        self.hlp = helpfile
        self.images = images
        self.image_dir = image_dir
        self.document = helpfile.get_document()
        self._font = getattr(helpfile, "font", None)
        self._topic_to_anchor: dict = {}
        self._style_class: dict = {}  # effective CSS rules -> css class name
        self._css_rules: dict = {}  # class name -> css body
        self._image_cache: dict = {}  # picture number -> <img> src or None
        self._image_map_count = 0

    # -- public ------------------------------------------------------------

    def export(self) -> str:
        topics = self.document.topics
        for i, t in enumerate(topics):
            anchor = self._anchor(t, i)
            self._topic_to_anchor[id(t)] = anchor

        sections = [self._render_topic(t, i, self._anchor(t, i)) for i, t in enumerate(topics)]
        toc = self._render_toc(topics)
        return self._document(toc + "\n" + "\n".join(sections))

    # -- document scaffold -------------------------------------------------

    def _title(self) -> str:
        sys = getattr(self.hlp, "system", None)
        return (sys.title if sys and sys.title else None) or "Windows Help"

    def _document(self, body: str) -> str:
        title = html.escape(self._title())
        # Font CSS is collected lazily during rendering, so build it last.
        font_css = "\n".join(f".{name} {{ {rules} }}" for name, rules in self._css_rules.items())
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
body {{ font-family: sans-serif; margin: 0 auto; max-width: 50em; padding: 1em; line-height: 1.4; }}
nav {{ border-bottom: 1px solid #ccc; margin-bottom: 2em; }}
nav ul {{ list-style: none; padding-left: 0; columns: 2; }}
section {{ border-top: 1px solid #eee; padding-top: 1em; margin-top: 2em; }}
.topic-meta {{ color: #888; font-size: 0.85em; }}
.nonscroll {{ background: #f6f6f6; padding: 0.5em; border-left: 3px solid #ccc; }}
table {{ border-collapse: collapse; margin: 1em 0; }}
td {{ border: 1px solid #ccc; padding: 0.3em 0.6em; vertical-align: top; }}
img {{ max-width: 100%; }}
a.popup {{ border-bottom: 1px dotted; }}
a.macro {{ color: inherit; text-decoration: none; cursor: default; }}
{font_css}
</style>
</head>
<body>
<h1>{title}</h1>
{body}
</body>
</html>
"""

    def _render_toc(self, topics) -> str:
        items = []
        for i, t in enumerate(topics):
            label = html.escape(t.title or f"Topic {t.topic_number if t.topic_number is not None else i}")
            items.append(f'<li><a href="#{self._anchor(t, i)}">{label}</a></li>')
        return "<nav>\n<ul>\n" + "\n".join(items) + "\n</ul>\n</nav>"

    # -- topics ------------------------------------------------------------

    @staticmethod
    def _anchor(topic, index: int) -> str:
        return f"topic-{index}"

    def _render_topic(self, topic, index: int, anchor: str) -> str:
        parts = [f'<section id="{anchor}">']
        if topic.title:
            parts.append(f"<h2>{html.escape(topic.title)}</h2>")
        meta = []
        if topic.context_names:
            meta.append("id: " + ", ".join(html.escape(c) for c in topic.context_names[:6]))
        if topic.keywords:
            meta.append("keywords: " + ", ".join(html.escape(k) for k in topic.keywords[:8]))
        if meta:
            parts.append(f'<p class="topic-meta">{" &middot; ".join(meta)}</p>')

        if topic.content_blocks:
            layout = layout_topic(topic)
            fixed = "\n".join(self._render_block(block) for block in layout.fixed_blocks)
            if fixed:
                parts.append(f'<div class="nonscroll">{fixed}</div>')
            parts.extend(self._render_block(block) for block in layout.scrolling_blocks)
        else:
            parts.append(self._render_spans(topic.text_spans))
            for table in topic.tables:
                parts.append(self._render_table(table))
        parts.append("</section>")
        return "\n".join(p for p in parts if p)

    def _render_block(self, block) -> str:
        if isinstance(block, TopicTextBlock):
            return self._render_spans(block.text_spans, block.paragraph_info)
        if isinstance(block, TopicTableBlock):
            return self._render_table(block.table)
        return ""

    def _render_spans(self, spans, paragraph_info=None) -> str:
        """Turn the topic's flat text_spans into <p> paragraphs of styled runs.

        Span text carries the paragraph structure the interleaved parser emitted:
        "\\n\\n" between paragraphs, "\\n" a line break, "\\t" a tab.
        """
        paragraphs = [[]]  # list of paragraphs; each a list of html run strings
        for span in spans:
            text = span.text or ""
            # Split into paragraph chunks, keeping run formatting per chunk.
            chunks = text.split("\n\n")
            for ci, chunk in enumerate(chunks):
                if ci > 0:
                    paragraphs.append([])
                # Render a run for any text, and for image-only spans (empty text
                # but an embedded picture) on their first chunk.
                if chunk or (ci == 0 and span.embedded_image):
                    paragraphs[-1].append(self._render_run(span, chunk))
        html_paras = []
        for runs in paragraphs:
            inner = "".join(runs).strip()
            if inner:
                style = self._paragraph_style(paragraph_info)
                attribute = f' style="{style}"' if style else ""
                html_paras.append(f"<p{attribute}>{inner}</p>")
        return "\n".join(html_paras)

    @staticmethod
    def _paragraph_style(paragraph) -> str:
        if paragraph is None:
            return ""
        declarations = []
        if paragraph.bits.center_aligned_paragraph:
            declarations.append("text-align: center")
        elif paragraph.bits.right_aligned_paragraph:
            declarations.append("text-align: right")
        for field, css in (
            (paragraph.left_indent, "margin-left"),
            (paragraph.right_indent, "margin-right"),
            (paragraph.firstline_indent, "text-indent"),
            (paragraph.spacing_above, "margin-top"),
            (paragraph.spacing_below, "margin-bottom"),
        ):
            if field:
                declarations.append(f"{css}: {field / 20:g}pt")
        if paragraph.spacing_lines and paragraph.spacing_lines > 0:
            declarations.append(f"line-height: {paragraph.spacing_lines / 20:g}pt")
        if paragraph.tab_info and paragraph.tab_info.tabs:
            first = max(1, paragraph.tab_info.tabs[0].position // 120)
            declarations.append(f"tab-size: {first}")
        border = paragraph.border_info
        if border:
            border_style = "double" if border.border_double else "solid"
            width = max(1, border.border_width)
            for enabled, side in (
                (border.border_box or border.border_top, "top"),
                (border.border_box or border.border_right, "right"),
                (border.border_box or border.border_bottom, "bottom"),
                (border.border_box or border.border_left, "left"),
            ):
                if enabled:
                    declarations.append(f"border-{side}: {width}px {border_style} currentColor")
        return "; ".join(declarations)

    def _render_run(self, span, text: str) -> str:
        # line break / tab inside a run
        safe = html.escape(text).replace("\n", "<br>").replace("\t", "&emsp;")
        cls = self._font_class_for(span)
        inner = f'<span class="{cls}">{safe}</span>' if cls else safe

        if span.embedded_image:
            img = self._render_image(span.embedded_image)
            if img:
                return inner + img if text.strip() else img
        if span.is_hyperlink and span.hyperlink_target:
            return self._render_hyperlink(span.hyperlink_target, inner)
        return inner

    # -- hyperlinks --------------------------------------------------------

    def _render_hyperlink(self, target: str, inner: str) -> str:
        resolved = self.document.resolve_target(target)
        if resolved.kind in ("topic", "popup"):
            anchor = self._topic_to_anchor.get(id(resolved.topic)) if resolved.topic is not None else None
            cls = "popup" if resolved.kind == "popup" else "jump"
            if anchor:
                return f'<a class="{cls}" href="#{anchor}">{inner}</a>'
            # unresolved jump: keep it visibly a link but inert
            return f'<a class="{cls}" title="{html.escape(target)}">{inner}</a>'
        if resolved.kind == "macro":
            macro = html.escape(resolved.detail or target)
            return f'<a class="macro" title="{macro}">{inner}</a>'
        return f'<a title="{html.escape(resolved.detail or target)}">{inner}</a>'

    # -- fonts / css -------------------------------------------------------

    def _font_class_for(self, span) -> Optional[str]:
        n = span.font_number
        attrs = {}
        if self._font is not None and n is not None:
            try:
                attrs = self._font.get_font_attributes(n)
            except Exception:
                attrs = {}
        rules = self._css_from_attrs(attrs, span)
        if not rules:
            return None
        if rules in self._style_class:
            return self._style_class[rules]
        name = f"f{len(self._style_class)}"
        self._style_class[rules] = name
        self._css_rules[name] = rules
        return name

    @staticmethod
    def _css_from_attrs(attrs, span) -> str:
        decls = []
        face = attrs.get("facename")
        if face:
            # CSS escapes preserve the name while keeping quotes/control bytes
            # inside the string and preventing HTML's raw-text </style> terminator.
            face = "".join(
                f"\\{ord(char):x} " if char in '\\"<' or ord(char) < 32 or ord(char) == 127 else char for char in face
            )
            decls.append(f'font-family: "{face}", serif')
        hp = attrs.get("half_points")
        if hp and hp > 0:
            decls.append(f"font-size: {hp / 2:.1f}pt")
        if attrs.get("bold") or span.is_bold:
            decls.append("font-weight: bold")
        if attrs.get("italic") or span.is_italic:
            decls.append("font-style: italic")
        decorations = []
        if attrs.get("underline") or attrs.get("double_underline") or span.is_underline or span.is_double_underline:
            decorations.append("underline")
        if attrs.get("strikethrough") or span.is_strikethrough:
            decorations.append("line-through")
        if decorations:
            decls.append("text-decoration: " + " ".join(decorations))
        if attrs.get("small_caps"):
            decls.append("font-variant: small-caps")
        if span.is_superscript:
            decls.extend(("vertical-align: super", "font-size: smaller"))
        elif span.is_subscript:
            decls.extend(("vertical-align: sub", "font-size: smaller"))
        fg = attrs.get("fg_rgb")
        if fg and fg != (0, 0, 0):
            decls.append("color: #%02x%02x%02x" % fg)
        bg = attrs.get("bg_rgb") or span.bg_rgb
        if bg and bg != (255, 255, 255):
            decls.append("background-color: #%02x%02x%02x" % bg)
        return "; ".join(decls)

    # -- tables ------------------------------------------------------------

    def _render_table(self, table) -> str:
        rows = []
        for row in table.rows:
            cells = []
            for cell in row.cells:
                content = self._render_spans(cell.text_spans, cell.paragraph_info)
                align = f' style="text-align: {cell.alignment}"' if cell.alignment != "left" else ""
                span = f' colspan="{cell.column_span}"' if cell.column_span > 1 else ""
                cells.append(f"<td{align}{span}>{content}</td>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        style = self._paragraph_style(table.table_formatting)
        attribute = f' style="{style}"' if style else ""
        return f"<table{attribute}>\n" + "\n".join(rows) + "\n</table>" if rows else ""

    # -- images ------------------------------------------------------------

    def _render_image(self, marker: str) -> str:
        resource = parse_embedded_resource(marker)
        if resource is None:
            return ""  # no resource reference to resolve

        bitmaps = getattr(self.hlp, "bitmaps", {}) or {}
        if resource.kind == "bitmap" and resource.reference.isdigit():
            ref = resource.reference
            key = f"|bm{ref}" if f"|bm{ref}" in bitmaps else f"bm{ref}"
            alt = f"bitmap {ref}"
        else:  # window: extract the filename from "DLL, Class, [!]Param"
            key = resource.resource_name
            alt = key or ""
        bitmap_file = bitmaps.get(key)
        src = self._image_src(bitmap_file, key)
        if not src:
            return ""
        style = _IMG_STYLE.get(resource.alignment, "")  # inline -> no float
        image_map = self._render_image_map(bitmap_file)
        usemap = f' usemap="#{image_map[0]}"' if image_map else ""
        image = f'<img{style}{usemap} src="{html.escape(src, quote=True)}" alt="{html.escape(alt)}">'
        return image + image_map[1] if image_map else image

    def _render_image_map(self, bitmap_file):
        """Render clickable SHG/MRB rectangles with the shared link resolver."""
        pictures = getattr(bitmap_file, "bitmaps", ()) if bitmap_file else ()
        hotspots = getattr(pictures[0], "hotspots", ()) if pictures else ()
        if not hotspots:
            return None
        name = f"image-map-{self._image_map_count}"
        self._image_map_count += 1
        areas = []
        for hotspot in hotspots:
            x2 = hotspot.x + max(0, hotspot.width)
            y2 = hotspot.y + max(0, hotspot.height)
            target = self.document.resolve_bitmap_hotspot(hotspot)
            anchor = self._topic_to_anchor.get(id(target.topic)) if target.topic is not None else None
            href = f' href="#{anchor}"' if anchor else ""
            label = hotspot.name or target.detail or hotspot.target or "image hotspot"
            areas.append(
                f'<area shape="rect" coords="{hotspot.x},{hotspot.y},{x2},{y2}"{href} '
                f'alt="{html.escape(label, quote=True)}" title="{html.escape(label, quote=True)}">'
            )
        return name, f'<map name="{name}">{"".join(areas)}</map>'

    def _image_src(self, bitmap_file, cache_key):
        if not cache_key or not bitmap_file:
            return None
        if cache_key in self._image_cache:
            return self._image_cache[cache_key]
        result = None
        try:
            extracted = bitmap_file.extract_image(0)
        except Exception:
            extracted = None
        if extracted:
            ext, data = extracted
            header = bitmap_file.bitmaps[0].header
            data, ext = _to_png(data, ext, (header.width, header.height))
            mime = {"bmp": "image/bmp", "wmf": "image/wmf", "png": "image/png"}.get(ext, "application/octet-stream")
            if self.images == "extract" and self.image_dir:
                os.makedirs(self.image_dir, exist_ok=True)
                fname = re.sub(r"[^\w.-]", "_", cache_key.lstrip("|")) + f".{ext}"
                with open(os.path.join(self.image_dir, fname), "wb") as fh:
                    fh.write(data)
                directory = os.path.basename(os.path.normpath(self.image_dir))
                result = f"{quote(directory, safe='')}/{quote(fname, safe='')}"
            else:
                b64 = base64.b64encode(data).decode("ascii")
                result = f"data:{mime};base64,{b64}"
        self._image_cache[cache_key] = result
        return result


def export_html(helpfile, images: str = "embed", image_dir: Optional[str] = None) -> str:
    """Render a HelpFile to a single HTML document string."""
    return HtmlExporter(helpfile, images=images, image_dir=image_dir).export()
