from __future__ import annotations

import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshot-placeholder.png"
WIDTH = 1280
HEIGHT = 760


Color = tuple[int, int, int]


def chunk(name: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)


def rect(pixels: list[bytearray], x: int, y: int, width: int, height: int, color: Color) -> None:
    r, g, b = color
    for row in range(max(0, y), min(HEIGHT, y + height)):
        line = pixels[row]
        for col in range(max(0, x), min(WIDTH, x + width)):
            offset = col * 3
            line[offset : offset + 3] = bytes((r, g, b))


def hline(pixels: list[bytearray], x: int, y: int, width: int, color: Color) -> None:
    rect(pixels, x, y, width, 1, color)


def vline(pixels: list[bytearray], x: int, y: int, height: int, color: Color) -> None:
    rect(pixels, x, y, 1, height, color)


def card(pixels: list[bytearray], x: int, y: int, width: int, height: int, fill: Color = (255, 255, 255)) -> None:
    rect(pixels, x, y, width, height, fill)
    hline(pixels, x, y, width, (217, 225, 236))
    hline(pixels, x, y + height - 1, width, (217, 225, 236))
    vline(pixels, x, y, height, (217, 225, 236))
    vline(pixels, x + width - 1, y, height, (217, 225, 236))


def bar(pixels: list[bytearray], x: int, y: int, width: int, color: Color = (100, 116, 139)) -> None:
    rect(pixels, x, y, width, 10, color)


def draw_mock_ui(pixels: list[bytearray]) -> None:
    navy = (16, 36, 63)
    teal = (22, 115, 90)
    slate = (100, 116, 139)
    pale = (242, 246, 251)
    border = (217, 225, 236)

    rect(pixels, 0, 0, WIDTH, HEIGHT, (245, 247, 251))
    rect(pixels, 0, 0, WIDTH, 112, navy)
    bar(pixels, 72, 34, 230, (159, 180, 207))
    rect(pixels, 72, 58, 390, 26, (255, 255, 255))
    card(pixels, 994, 32, 142, 40, (23, 50, 82))
    card(pixels, 1150, 32, 74, 40, (23, 50, 82))

    card(pixels, 72, 144, 810, 214)
    bar(pixels, 100, 174, 180, slate)
    card(pixels, 100, 204, 740, 86, (248, 250, 252))
    bar(pixels, 124, 226, 520, (51, 65, 85))
    bar(pixels, 124, 250, 440, (71, 85, 105))
    rect(pixels, 100, 310, 120, 38, teal)
    rect(pixels, 234, 310, 146, 38, (231, 237, 245))

    card(pixels, 902, 144, 306, 214, pale)
    for index, value_width in enumerate([120, 96, 164, 118]):
        y = 172 + index * 42
        bar(pixels, 932, y, 88, slate)
        rect(pixels, 1042, y - 4, value_width, 18, navy)

    card(pixels, 72, 382, 1136, 120)
    bar(pixels, 100, 414, 160, slate)
    rect(pixels, 100, 444, 188, 34, teal)
    for index, value_width in enumerate([112, 98, 98, 98, 98]):
        x = 340 + index * 156
        card(pixels, x, 416, 126, 58, (248, 250, 252))
        rect(pixels, x + 16, 436, value_width, 16, navy)

    card(pixels, 72, 528, 548, 146)
    bar(pixels, 100, 558, 130, slate)
    for index, width in enumerate([450, 396, 472]):
        bar(pixels, 100, 590 + index * 25, width, (51, 65, 85))

    card(pixels, 644, 528, 564, 146)
    bar(pixels, 672, 558, 120, slate)
    for index, color in enumerate([(194, 65, 12), (217, 119, 6)]):
        rect(pixels, 672, 590 + index * 36, 5, 24, color)
        bar(pixels, 690, 596 + index * 36, 380, (51, 65, 85))

    rect(pixels, 72, 700, 1136, 1, border)


def write_png(path: Path) -> None:
    pixels = [bytearray((245, 247, 251) * WIDTH) for _ in range(HEIGHT)]
    draw_mock_ui(pixels)
    raw = b"".join(b"\x00" + bytes(row) for row in pixels)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, level=9))
    png += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def main() -> None:
    write_png(OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
