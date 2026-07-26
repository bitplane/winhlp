"""Small replaceable terminal rasterizer for Windows bitmap resources."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional, Protocol, Sequence

from rich.style import Style
from rich.text import Text


RGB = tuple[int, int, int]


@dataclass(frozen=True)
class RasterImage:
    width: int
    height: int
    pixels: tuple[RGB, ...]

    def pixel(self, x: int, y: int) -> RGB:
        x = min(max(x, 0), self.width - 1)
        y = min(max(y, 0), self.height - 1)
        return self.pixels[y * self.width + x]


@dataclass(frozen=True)
class RasterHotspot:
    x: int
    y: int
    width: int
    height: int
    action: Optional[str] = None
    reverse_on_select: bool = True

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.width and self.y <= y < self.y + self.height


class TerminalRasterizer(Protocol):
    def render(
        self,
        image: RasterImage,
        max_width: int,
        hotspots: Sequence[RasterHotspot] = (),
        selected_hotspot: int = -1,
    ) -> Text: ...


def decode_bmp(data: bytes) -> Optional[RasterImage]:
    """Decode uncompressed indexed or true-colour Windows BMP data."""
    if len(data) < 54 or data[:2] != b"BM":
        return None
    try:
        pixel_offset = struct.unpack_from("<I", data, 10)[0]
        dib_size = struct.unpack_from("<I", data, 14)[0]
        width = struct.unpack_from("<i", data, 18)[0]
        signed_height = struct.unpack_from("<i", data, 22)[0]
        planes, bit_count = struct.unpack_from("<HH", data, 26)
        compression = struct.unpack_from("<I", data, 30)[0]
        colors_used = struct.unpack_from("<I", data, 46)[0] if dib_size >= 40 else 0
    except struct.error:
        return None
    if planes != 1 or width <= 0 or signed_height == 0 or compression != 0 or bit_count not in (1, 4, 8, 24, 32):
        return None

    height = abs(signed_height)
    top_down = signed_height < 0
    row_size = ((width * bit_count + 31) // 32) * 4
    if pixel_offset + row_size * height > len(data):
        return None

    palette: list[RGB] = []
    if bit_count <= 8:
        count = colors_used or 1 << bit_count
        palette_start = 14 + dib_size
        if palette_start + count * 4 > pixel_offset:
            return None
        for index in range(count):
            blue, green, red, _ = struct.unpack_from("<BBBB", data, palette_start + index * 4)
            palette.append((red, green, blue))

    pixels: list[RGB] = []
    for display_y in range(height):
        source_y = display_y if top_down else height - 1 - display_y
        row = pixel_offset + source_y * row_size
        for x in range(width):
            if bit_count <= 8:
                if bit_count == 1:
                    palette_index = (data[row + x // 8] >> (7 - x % 8)) & 0x01
                elif bit_count == 4:
                    packed = data[row + x // 2]
                    palette_index = packed >> 4 if x % 2 == 0 else packed & 0x0F
                else:
                    palette_index = data[row + x]
                pixels.append(palette[palette_index] if palette_index < len(palette) else (0, 0, 0))
            elif bit_count == 24:
                blue, green, red = struct.unpack_from("<BBB", data, row + x * 3)
                pixels.append((red, green, blue))
            else:
                blue, green, red, _ = struct.unpack_from("<BBBB", data, row + x * 4)
                pixels.append((red, green, blue))
    return RasterImage(width, height, tuple(pixels))


class HalfBlockRasterizer:
    """Render two sampled image rows per terminal cell with ``▀``."""

    def __init__(self, max_height: int = 30):
        self.max_height = max_height

    def render(
        self,
        image: RasterImage,
        max_width: int,
        hotspots: Sequence[RasterHotspot] = (),
        selected_hotspot: int = -1,
    ) -> Text:
        if max_width <= 0:
            return Text()
        output_width = min(image.width, max_width)
        scale = image.width / output_width
        output_height = min(self.max_height, max(1, round(image.height / scale / 2)))
        y_scale = image.height / (output_height * 2)

        text = Text()
        for row in range(output_height):
            for column in range(output_width):
                source_x = min(image.width - 1, int((column + 0.5) * scale))
                top_y = min(image.height - 1, int((row * 2 + 0.5) * y_scale))
                bottom_y = min(image.height - 1, int((row * 2 + 1.5) * y_scale))
                hotspot_index = next(
                    (
                        i
                        for i, hotspot in enumerate(hotspots)
                        if hotspot.contains(source_x, top_y) or hotspot.contains(source_x, bottom_y)
                    ),
                    -1,
                )
                action = hotspots[hotspot_index].action if hotspot_index >= 0 else None
                is_selected = hotspot_index >= 0 and hotspot_index == selected_hotspot
                reverse_on_select = hotspots[hotspot_index].reverse_on_select if hotspot_index >= 0 else False
                style = Style(
                    color=_rich_color(image.pixel(source_x, top_y)),
                    bgcolor=_rich_color(image.pixel(source_x, bottom_y)),
                    reverse=is_selected and reverse_on_select,
                    bold=is_selected,
                    meta={"@click": action} if action else None,
                )
                text.append("▀", style)
            if row + 1 < output_height:
                text.append("\n")
        return text


def _rich_color(rgb: RGB) -> str:
    return f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"
