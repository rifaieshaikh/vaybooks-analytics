"""Write a simple 256x256 PNG icon for the Windows build."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

W = H = 256
BG = (15, 61, 46, 255)
FG = (31, 107, 74, 255)
INK = (255, 255, 255, 255)


def chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def inside_round_rect(x: int, y: int, x0: int, y0: int, x1: int, y1: int, r: int) -> bool:
    if x0 + r <= x < x1 - r and y0 <= y < y1:
        return True
    if x0 <= x < x1 and y0 + r <= y < y1 - r:
        return True
    corners = ((x0 + r, y0 + r), (x1 - r - 1, y0 + r), (x0 + r, y1 - r - 1), (x1 - r - 1, y1 - r - 1))
    for cx, cy in corners:
        if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
            return True
    return False


def color(x: int, y: int) -> tuple[int, int, int, int]:
    if not inside_round_rect(x, y, 8, 8, W - 8, H - 8, 40):
        return (0, 0, 0, 0)
    if not inside_round_rect(x, y, 28, 28, W - 28, H - 28, 28):
        return BG
    # Chevron V
    cx, cy = W // 2, 92
    thickness = 22
    left = abs((y - cy) - (x - 56)) <= thickness and 70 <= y <= 190 and x <= cx + 8
    right = abs((y - cy) - (W - 56 - x)) <= thickness and 70 <= y <= 190 and x >= cx - 8
    if left or right:
        return INK
    return FG


def main() -> None:
    raw = bytearray()
    for y in range(H):
        raw.append(0)
        for x in range(W):
            raw.extend(color(x, y))
    ihdr = struct.pack(">IIBBBBB", W, H, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    out = Path(__file__).resolve().parents[1] / "build" / "icon.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    print("wrote", out)


if __name__ == "__main__":
    main()
