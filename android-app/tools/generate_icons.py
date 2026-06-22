#!/usr/bin/env python3
# =============================================================================
#  Generate PNG launcher icons for the Exact Hour app (no Pillow needed).
# -----------------------------------------------------------------------------
#  minSdk 26 uses the adaptive (vector) icon, so these PNGs are fallbacks. They
#  reproduce the same design as ic_launcher_foreground.xml: a near-black tile
#  with an amber "LED display" outline and a colon.
#
#  Pure standard library: we rasterise at 4x supersampling for smooth edges and
#  encode PNG by hand with zlib. Run:  py android-app/tools/generate_icons.py
# =============================================================================

import os
import struct
import zlib

BG = (11, 11, 13, 255)        # #0B0B0D
AM = (255, 176, 32, 255)      # #FFB020
CLEAR = (0, 0, 0, 0)

DENSITIES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
SS = 4                         # supersampling factor


def inside_round_rect(px, py, x0, y0, x1, y1, r):
    if px < x0 or px > x1 or py < y0 or py > y1:
        return False
    cx = min(max(px, x0 + r), x1 - r)
    cy = min(max(py, y0 + r), y1 - r)
    dx, dy = px - cx, py - cy
    return dx * dx + dy * dy <= r * r


def fill_round_rect(buf, W, x0, y0, x1, y1, r, color):
    ix0, iy0 = max(0, int(x0)), max(0, int(y0))
    ix1, iy1 = min(W, int(x1) + 1), min(W, int(y1) + 1)
    for y in range(iy0, iy1):
        for x in range(ix0, ix1):
            if inside_round_rect(x + 0.5, y + 0.5, x0, y0, x1, y1, r):
                i = (y * W + x) * 4
                buf[i], buf[i + 1], buf[i + 2], buf[i + 3] = color


def fill_circle(buf, W, cx, cy, rad, color):
    iy0, iy1 = max(0, int(cy - rad)), min(W, int(cy + rad) + 1)
    for y in range(iy0, iy1):
        dy = y + 0.5 - cy
        span = rad * rad - dy * dy
        if span < 0:
            continue
        hw = span ** 0.5
        for x in range(max(0, int(cx - hw)), min(W, int(cx + hw) + 1)):
            dx = x + 0.5 - cx
            if dx * dx + dy * dy <= rad * rad:
                i = (y * W + x) * 4
                buf[i], buf[i + 1], buf[i + 2], buf[i + 3] = color


def downsample(buf, W, S, ss):
    """Box-downsample with alpha-weighted RGB (so edges don't pick up dark fringe)."""
    out = bytearray(S * S * 4)
    n = ss * ss
    for oy in range(S):
        for ox in range(S):
            rw = gw = bw = a = 0
            base_y = oy * ss
            base_x = ox * ss
            for j in range(ss):
                row = (base_y + j) * W
                for i in range(ss):
                    idx = (row + base_x + i) * 4
                    al = buf[idx + 3]
                    rw += buf[idx] * al
                    gw += buf[idx + 1] * al
                    bw += buf[idx + 2] * al
                    a += al
            o = (oy * S + ox) * 4
            if a == 0:
                out[o] = out[o + 1] = out[o + 2] = out[o + 3] = 0
            else:
                out[o] = rw // a
                out[o + 1] = gw // a
                out[o + 2] = bw // a
                out[o + 3] = a // n
    return out


def render(S, round_icon):
    W = S * SS
    sc = W / 108.0
    buf = bytearray(W * W * 4)              # starts fully transparent
    if round_icon:
        fill_circle(buf, W, 54 * sc, 54 * sc, 54 * sc, BG)
    else:
        fill_round_rect(buf, W, 0, 0, W, W, 14 * sc, BG)
    # amber "display" outline = outer amber rect with a background rect carved out
    fill_round_rect(buf, W, 26 * sc, 40 * sc, 82 * sc, 68 * sc, 6 * sc, AM)
    fill_round_rect(buf, W, 29.5 * sc, 43.5 * sc, 78.5 * sc, 64.5 * sc, 3 * sc, BG)
    # colon
    fill_round_rect(buf, W, 51 * sc, 47 * sc, 57 * sc, 52 * sc, 1.3 * sc, AM)
    fill_round_rect(buf, W, 51 * sc, 56 * sc, 57 * sc, 61 * sc, 1.3 * sc, AM)
    return downsample(buf, W, S, SS)


def write_png(path, S, pixels):
    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff))
    raw = bytearray()
    for y in range(S):
        raw.append(0)                      # filter type 0 for each scanline
        raw.extend(pixels[y * S * 4:(y + 1) * S * 4])
    ihdr = struct.pack(">IIBBBBB", S, S, 8, 6, 0, 0, 0)   # 8-bit RGBA
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        f.write(chunk(b"IEND", b""))


def main():
    res = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "..", "app", "src", "main", "res"))
    for density, size in DENSITIES.items():
        folder = os.path.join(res, "mipmap-" + density)
        os.makedirs(folder, exist_ok=True)
        for name, is_round in (("ic_launcher", False), ("ic_launcher_round", True)):
            path = os.path.join(folder, name + ".png")
            write_png(path, size, render(size, is_round))
            print("wrote {} ({}x{})".format(os.path.relpath(path, res), size, size))


if __name__ == "__main__":
    main()
