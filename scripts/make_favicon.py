from __future__ import annotations

import struct
from pathlib import Path


SIZE = 32
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "favicon.ico"


def inside_rect(x: int, y: int, left: int, top: int, right: int, bottom: int) -> bool:
    return left <= x < right and top <= y < bottom


def inside_circle(x: int, y: int, cx: float, cy: float, r: float) -> bool:
    return (x - cx) ** 2 + (y - cy) ** 2 <= r ** 2


def inside_polygon(x: int, y: int, points: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(points) - 1
    for i, (xi, yi) in enumerate(points):
        xj, yj = points[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def pixel(x: int, y: int) -> tuple[int, int, int, int]:
    navy = (16, 36, 63, 255)
    teal = (18, 116, 110, 255)
    white = (248, 250, 252, 255)
    slate = (226, 232, 240, 255)
    dark = (37, 57, 86, 255)

    color = navy

    # Document sheet
    if inside_rect(x, y, 9, 6, 23, 24):
        color = white
    if inside_polygon(x, y, [(18, 6), (23, 6), (23, 11)]):
        color = slate
    if inside_rect(x, y, 20, 8, 22, 10):
        color = slate
    if inside_rect(x, y, 12, 12, 20, 13):
        color = dark
    if inside_rect(x, y, 12, 15, 19, 16):
        color = dark
    if inside_rect(x, y, 12, 18, 18, 19):
        color = dark

    # Shield
    shield = inside_polygon(
        x,
        y,
        [
            (18, 16),
            (27, 16),
            (27, 21),
            (22.5, 27),
            (18, 21),
        ],
    )
    if shield:
        color = teal

    # Shield check
    if inside_rect(x, y, 21, 20, 22, 21):
        color = white
    if inside_rect(x, y, 20, 21, 21, 22):
        color = white
    if inside_rect(x, y, 22, 19, 23, 20):
        color = white
    if inside_rect(x, y, 23, 18, 24, 19):
        color = white
    if inside_rect(x, y, 24, 19, 25, 20):
        color = white
    if inside_rect(x, y, 25, 20, 26, 21):
        color = white

    return color


def build_ico() -> bytes:
    pixels = []
    for y in range(SIZE - 1, -1, -1):
        row = bytearray()
        for x in range(SIZE):
            r, g, b, a = pixel(x, y)
            row.extend([b, g, r, a])
        pixels.append(bytes(row))
    xor = b"".join(pixels)
    and_mask_row_bytes = ((SIZE + 31) // 32) * 4
    and_mask = b"\x00" * and_mask_row_bytes * SIZE
    header = struct.pack("<HHH", 0, 1, 1)
    dib = struct.pack(
        "<IIIHHIIIIII",
        40,
        SIZE,
        SIZE * 2,
        1,
        32,
        0,
        len(xor) + len(and_mask),
        2835,
        2835,
        0,
        0,
    )
    image_data = dib + xor + and_mask
    offset = 6 + 16
    entry = struct.pack("<BBBBHHII", SIZE if SIZE < 256 else 0, SIZE if SIZE < 256 else 0, 0, 0, 1, 32, len(image_data), offset)
    return header + entry + image_data


def main() -> None:
    OUT.write_bytes(build_ico())
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
