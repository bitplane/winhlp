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

try:
    from PIL import Image

    _HAVE_PIL = True
except ImportError:  # pragma: no cover - optional dependency
    _HAVE_PIL = False


def _to_png(data: bytes, ext: str) -> tuple:
    """Convert a decoded bitmap to PNG when Pillow is available.

    PNG is smaller (our BMPs are uncompressed) and renders everywhere; if Pillow
    is missing or can't decode the image (e.g. a WMF metafile) we keep the
    original bytes. Returns (bytes, ext).
    """
    if not _HAVE_PIL or ext != "bmp":
        return data, ext
    try:
        with Image.open(io.BytesIO(data)) as img:
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


def _ewc_filename(ewc: str) -> str:
    """Pull the resource filename out of an ewc "DLL, Class, [!]Param" string.

    MediaView bitmap DLLs (e.g. MVBMP2) name the actual bitmap in the last field,
    often prefixed with '!' — e.g. "MVBMP2, ViewerBmp2, !cvr_nec5.shg".
    """
    last = ewc.split(",")[-1].strip()
    return last.lstrip("!").strip()


class HtmlExporter:
    def __init__(self, helpfile, images: str = "embed", image_dir: Optional[str] = None):
        """images: "embed" (data URIs) or "extract" (write files to image_dir)."""
        self.hlp = helpfile
        self.images = images
        self.image_dir = image_dir
        self._font = getattr(helpfile, "font", None)
        self._offset_to_anchor: dict = {}
        self._font_class: dict = {}  # font_number -> css class name
        self._css_rules: dict = {}  # class name -> css body
        self._image_cache: dict = {}  # picture number -> <img> src or None

    # -- public ------------------------------------------------------------

    def export(self) -> str:
        topics = self.hlp.topic.get_all_topics() if self.hlp.topic else []
        for i, t in enumerate(topics):
            anchor = self._anchor(t, i)
            if t.topic_offset is not None:
                self._offset_to_anchor.setdefault(t.topic_offset, anchor)

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

        parts.append(self._render_spans(topic))
        for table in topic.tables:
            parts.append(self._render_table(table))
        parts.append("</section>")
        return "\n".join(p for p in parts if p)

    def _render_spans(self, topic) -> str:
        """Turn the topic's flat text_spans into <p> paragraphs of styled runs.

        Span text carries the paragraph structure the interleaved parser emitted:
        "\\n\\n" between paragraphs, "\\n" a line break, "\\t" a tab.
        """
        paragraphs = [[]]  # list of paragraphs; each a list of html run strings
        for span in topic.text_spans:
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
                html_paras.append(f"<p>{inner}</p>")
        return "\n".join(html_paras)

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
        if target.startswith(("topic:", "popup:")):
            kind, _, ref = target.partition(":")
            anchor = self._resolve_offset_ref(ref)
            cls = "popup" if kind == "popup" else "jump"
            if anchor:
                return f'<a class="{cls}" href="#{anchor}">{inner}</a>'
            # unresolved jump: keep it visibly a link but inert
            return f'<a class="{cls}" title="{html.escape(target)}">{inner}</a>'
        if target.startswith("macro:"):
            macro = html.escape(target[len("macro:") :])
            return f'<a class="macro" title="{macro}">{inner}</a>'
        return f'<a title="{html.escape(target)}">{inner}</a>'

    def _resolve_offset_ref(self, ref: str) -> Optional[str]:
        # ref is either an 8-hex TOPICOFFSET or "TOPIC<n>" (HC30).
        try:
            offset = int(ref, 16) if all(c in "0123456789ABCDEFabcdef" for c in ref) else None
        except ValueError:
            offset = None
        if offset is None:
            return None
        if offset in self._offset_to_anchor:
            return self._offset_to_anchor[offset]
        # nearest topic at or before this offset (topic covers a range)
        below = [o for o in self._offset_to_anchor if o <= offset]
        return self._offset_to_anchor[max(below)] if below else None

    # -- fonts / css -------------------------------------------------------

    def _font_class_for(self, span) -> Optional[str]:
        n = span.font_number
        if n is None:
            key = self._span_style_key(span, {})
            if not key:
                return None
        if n in self._font_class:
            return self._font_class[n] if n is not None else None
        attrs = {}
        if self._font is not None and n is not None:
            try:
                attrs = self._font.get_font_attributes(n)
            except Exception:
                attrs = {}
        rules = self._css_from_attrs(attrs, span)
        if not rules:
            if n is not None:
                self._font_class[n] = None
            return None
        name = f"f{n if n is not None else 'x'}"
        self._font_class[n] = name
        self._css_rules[name] = rules
        return name

    @staticmethod
    def _span_style_key(span, attrs) -> str:
        return "".join(
            "1" if getattr(span, a, False) else "0"
            for a in ("is_bold", "is_italic", "is_underline", "is_strikethrough")
        )

    @staticmethod
    def _css_from_attrs(attrs, span) -> str:
        decls = []
        face = attrs.get("facename")
        if face:
            decls.append(f'font-family: "{face}", serif')
        hp = attrs.get("half_points")
        if hp and hp > 0:
            decls.append(f"font-size: {hp / 2:.1f}pt")
        if attrs.get("bold") or span.is_bold:
            decls.append("font-weight: bold")
        if attrs.get("italic") or span.is_italic:
            decls.append("font-style: italic")
        decorations = []
        if attrs.get("underline") or attrs.get("double_underline") or span.is_underline:
            decorations.append("underline")
        if attrs.get("strikethrough") or span.is_strikethrough:
            decorations.append("line-through")
        if decorations:
            decls.append("text-decoration: " + " ".join(decorations))
        if attrs.get("small_caps"):
            decls.append("font-variant: small-caps")
        fg = attrs.get("fg_rgb")
        if fg and fg != (0, 0, 0):
            decls.append("color: #%02x%02x%02x" % fg)
        return "; ".join(decls)

    # -- tables ------------------------------------------------------------

    def _render_table(self, table) -> str:
        rows = []
        for row in table.rows:
            cells = []
            for cell in row.cells:
                text = "".join(s.text for s in cell.text_spans)
                align = f' style="text-align: {cell.alignment}"' if cell.alignment != "left" else ""
                span = f' colspan="{cell.column_span}"' if cell.column_span > 1 else ""
                cells.append(f"<td{align}{span}>{html.escape(text).replace(chr(10), '<br>')}</td>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        return "<table>\n" + "\n".join(rows) + "\n</table>" if rows else ""

    # -- images ------------------------------------------------------------

    def _render_image(self, marker: str) -> str:
        parts = marker.split(":", 2)
        if len(parts) < 3:
            return ""  # no resource reference to resolve
        kind, align, ref = parts[0], parts[1], parts[2]

        bitmaps = getattr(self.hlp, "bitmaps", {}) or {}
        if kind == "bitmap" and ref.isdigit():
            key = f"|bm{ref}" if f"|bm{ref}" in bitmaps else f"bm{ref}"
            alt = f"bitmap {ref}"
        else:  # window: extract the filename from "DLL, Class, [!]Param"
            key = _ewc_filename(ref)
            alt = key or ""
        src = self._image_src(bitmaps.get(key), key)
        if not src:
            return ""
        style = _IMG_STYLE.get(align, "")  # inline -> no float
        return f'<img{style} src="{src}" alt="{html.escape(alt)}">'

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
            data, ext = _to_png(data, ext)
            mime = {"bmp": "image/bmp", "wmf": "image/wmf", "png": "image/png"}.get(ext, "application/octet-stream")
            if self.images == "extract" and self.image_dir:
                os.makedirs(self.image_dir, exist_ok=True)
                fname = re.sub(r"[^\w.-]", "_", cache_key.lstrip("|")) + f".{ext}"
                with open(os.path.join(self.image_dir, fname), "wb") as fh:
                    fh.write(data)
                result = f"{os.path.basename(self.image_dir)}/{fname}"
            else:
                b64 = base64.b64encode(data).decode("ascii")
                result = f"data:{mime};base64,{b64}"
        self._image_cache[cache_key] = result
        return result


def export_html(helpfile, images: str = "embed", image_dir: Optional[str] = None) -> str:
    """Render a HelpFile to a single HTML document string."""
    return HtmlExporter(helpfile, images=images, image_dir=image_dir).export()
