#!/usr/bin/env python3
"""VELMARA - The Low Sun Isles.

A travel poster for a place that does not exist: a sunset lagoon where
islands float above calm water, their waterfalls pouring into the sea
beneath a low, amber sun.

Pure stdlib (zlib + struct). Deterministic: no randomness, no time, no
network. Running this twice produces byte-identical output.
Writes /output/entry.png, 1024x1024, under 1 MiB.
"""

import os
import struct
import zlib

W = 1024
H = 1024
HORIZON = 640  # y of the sea line

# ---------------------------------------------------------------- palette
# Sky gradient stops: (t, r, g, b), t = 0 at top, 1 at horizon.
SKY = [
    (0.00, 26, 18, 64),
    (0.25, 64, 34, 96),
    (0.45, 128, 58, 112),
    (0.65, 196, 88, 104),
    (0.82, 240, 140, 96),
    (1.00, 255, 196, 130),
]
# Sea gradient stops: t = 0 at horizon, 1 at bottom.
SEA = [
    (0.00, 250, 178, 110),
    (0.12, 214, 128, 92),
    (0.35, 120, 84, 96),
    (0.65, 48, 58, 92),
    (1.00, 22, 30, 62),
]

SUN_X, SUN_Y, SUN_R = 800, 320, 56
SUN_CORE = (255, 250, 230)
SUN_EDGE = (255, 214, 150)

NAME_CREAM = (255, 241, 214)
NAME_SHADOW = (30, 16, 52)

# ---------------------------------------------------------------- helpers
def lerp(a, b, t):
    return a + (b - a) * t


def grad(stops, t):
    """Interpolate a gradient stop list at t in [0, 1]."""
    if t <= stops[0][0]:
        return stops[0][1], stops[0][2], stops[0][3]
    for i in range(1, len(stops)):
        t0, r0, g0, b0 = stops[i - 1]
        t1, r1, g1, b1 = stops[i]
        if t <= t1:
            f = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            return (int(lerp(r0, r1, f)), int(lerp(g0, g1, f)),
                    int(lerp(b0, b1, f)))
    return stops[-1][1], stops[-1][2], stops[-1][3]


def clamp255(v):
    return 0 if v < 0 else (255 if v > 255 else v)


def hash2(x, y):
    """Deterministic integer hash for grain / sparkle (no random module)."""
    h = (x * 374761393 + y * 668265263) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return h


# ---------------------------------------------------------------- canvas
# img[y] is a bytearray of 3*W bytes (RGB).
img = [bytearray(W * 3) for _ in range(H)]


def set_px(x, y, r, g, b):
    if 0 <= x < W and 0 <= y < H:
        o = x * 3
        row = img[y]
        row[o] = clamp255(r)
        row[o + 1] = clamp255(g)
        row[o + 2] = clamp255(b)


def blend_px(x, y, r, g, b, a):
    """Alpha-blend a colour over the pixel (a in 0..1)."""
    if 0 <= x < W and 0 <= y < H and a > 0.0:
        o = x * 3
        row = img[y]
        ia = 1.0 - a
        row[o] = clamp255(int(row[o] * ia + r * a))
        row[o + 1] = clamp255(int(row[o + 1] * ia + g * a))
        row[o + 2] = clamp255(int(row[o + 2] * ia + b * a))


def fill_rect(x0, y0, x1, y1, r, g, b):
    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(W, x1)
    y1 = min(H, y1)
    for y in range(y0, y1):
        row = img[y]
        for x in range(x0, x1):
            o = x * 3
            row[o] = r
            row[o + 1] = g
            row[o + 2] = b


def disc(cx, cy, rad, r, g, b):
    """Filled disc, clipped."""
    r2 = rad * rad
    for y in range(max(0, cy - rad), min(H, cy + rad + 1)):
        dy = y - cy
        dx = int((r2 - dy * dy) ** 0.5)
        fill_rect(cx - dx, y, cx + dx + 1, y + 1, r, g, b)


def ellipse_alpha(cx, cy, rx, ry, r, g, b, a0):
    """Soft ellipse with quadratic falloff alpha."""
    for y in range(max(0, cy - ry), min(H, cy + ry + 1)):
        ny = (y - cy) / ry
        ny2 = ny * ny
        if ny2 >= 1.0:
            continue
        dx = int(rx * (1.0 - ny2) ** 0.5)
        for x in range(max(0, cx - dx), min(W, cx + dx + 1)):
            nx = (x - cx) / rx
            d2 = nx * nx + ny2
            if d2 >= 1.0:
                continue
            a = a0 * (1.0 - d2) * (1.0 - d2)
            blend_px(x, y, r, g, b, a)


# ---------------------------------------------------------------- base
def paint_base():
    for y in range(H):
        row = img[y]
        if y < HORIZON:
            # Sky, with a tiny per-row jitter so the gradient cannot band.
            t = y / HORIZON
            r, g, b = grad(SKY, t)
            j = (hash2(7, y) & 3) - 1
            r = clamp255(r + j)
            g = clamp255(g + j)
            b = clamp255(b + j)
            row[:] = bytes((r, g, b)) * W
        else:
            t = (y - HORIZON) / (H - HORIZON)
            r, g, b = grad(SEA, t)
            j = (hash2(11, y) & 3) - 1
            r = clamp255(r + j)
            g = clamp255(g + j)
            b = clamp255(b + j)
            # Faint swell lines every ~26 rows, stronger near the horizon.
            if (y - HORIZON) % 26 == 0:
                r = clamp255(r + 10)
                g = clamp255(g + 8)
                b = clamp255(b + 5)
            row[:] = bytes((r, g, b)) * W


# ---------------------------------------------------------------- clouds
CLOUDS = [
    # cx, cy, rx, ry, r, g, b, alpha
    (250, 300, 190, 22, 255, 178, 158, 0.30),
    (700, 205, 230, 18, 255, 190, 170, 0.26),
    (480, 118, 150, 13, 244, 164, 168, 0.22),
    (860, 440, 165, 15, 250, 172, 140, 0.28),
    (120, 150, 130, 12, 220, 140, 160, 0.20),
]


def paint_clouds():
    for (cx, cy, rx, ry, r, g, b, a) in CLOUDS:
        ellipse_alpha(cx, cy, rx, ry, r, g, b, a)


# ---------------------------------------------------------------- sun
def paint_sun():
    glow_r = 210
    for y in range(max(0, SUN_Y - glow_r), min(HORIZON, SUN_Y + glow_r + 1)):
        dy = y - SUN_Y
        for x in range(max(0, SUN_X - glow_r), min(W, SUN_X + glow_r + 1)):
            dx = x - SUN_X
            d2 = dx * dx + dy * dy
            if d2 >= glow_r * glow_r:
                continue
            d = d2 ** 0.5
            # Warm glow, strongest near the disc.
            a = 0.32 * (1.0 - d / glow_r) ** 2
            blend_px(x, y, 255, 196, 120, a)
    disc(SUN_X, SUN_Y, SUN_R, *SUN_EDGE)
    disc(SUN_X, SUN_Y, SUN_R - 8, *SUN_CORE)


# ---------------------------------------------------------------- islands
# Each island: cx, top_y, top_w (plateau width), plateau_h, bottom_y (point).
ISLANDS = [
    (470, 430, 470, 34, 645),   # main island, centre
    (120, 470, 190, 22, 560),   # left, hazier and smaller
    (895, 520, 170, 18, 600),   # right, small
]


def island_span(island, y):
    """Return (x0, x1) of the island at row y, or None."""
    cx, top_y, top_w, plateau_h, bottom_y = island
    if y < top_y or y > bottom_y:
        return None
    if y < top_y + plateau_h:
        # Plateau: slightly rounded top edge.
        f = (y - top_y) / plateau_h  # 0..1 down the plateau
        w = top_w * (0.92 + 0.08 * f)
        return (int(cx - w / 2), int(cx + w / 2))
    # Rock underside: tapers to a point, with a gentle curve.
    f = (y - top_y - plateau_h) / (bottom_y - top_y - plateau_h)
    w = top_w * (1.0 - f) ** 1.35
    # Slight asymmetry: the point drifts a little left.
    drift = -18 * f * f
    return (int(cx - w / 2 + drift), int(cx + w / 2 + drift))


def paint_islands():
    for idx, island in enumerate(ISLANDS):
        cx, top_y, top_w, plateau_h, bottom_y = island
        haze = 0.0 if idx == 0 else (0.60 if idx == 1 else 0.55)  # side islands fade into the haze
        for y in range(top_y, bottom_y + 1):
            span = island_span(island, y)
            if span is None:
                continue
            x0, x1 = span
            if y < top_y + plateau_h:
                # Sunlit plateau: warm gold-green turf, bright rim on top.
                if y < top_y + 5:
                    r, g, b = 238, 198, 118
                else:
                    r, g, b = 190, 158, 92
            else:
                # Rock: warm brown-violet darkening toward the point.
                f = (y - top_y - plateau_h) / (bottom_y - top_y - plateau_h)
                r = int(lerp(124, 66, f))
                g = int(lerp(80, 44, f))
                b = int(lerp(84, 68, f))
                # Faint vertical striations.
                s = (hash2(x0, y) & 7) - 3
                r = clamp255(r + s)
                g = clamp255(g + s)
                b = clamp255(b + s)
            row = img[y]
            for x in range(max(0, x0), min(W, x1)):
                o = x * 3
                if haze:
                    # Blend toward the sky colour behind it.
                    br, bg, bb = row[o], row[o + 1], row[o + 2]
                    row[o] = int(lerp(br, r, 1.0 - haze))
                    row[o + 1] = int(lerp(bg, g, 1.0 - haze))
                    row[o + 2] = int(lerp(bb, b, 1.0 - haze))
                else:
                    row[o] = r
                    row[o + 1] = g
                    row[o + 2] = b
    # A small stone watch-spire on the main island's plateau.
    spire_x, spire_top = 470, 398
    for y in range(spire_top, 430):
        wdt = 7 if y < 406 else 10
        fill_rect(spire_x - wdt, y, spire_x + wdt + 1, y + 1, 58, 38, 58)
    disc(spire_x, spire_top, 6, 58, 38, 58)


# ---------------------------------------------------------------- waterfalls
def paint_waterfalls():
    # (x at plateau edge, top y, bottom y, width)
    falls = [
        (240, 464, 760, 9),
        (700, 464, 760, 8),
        (30, 492, 640, 6),
        (972, 538, 660, 6),
    ]
    for (fx, top, bottom, wdt) in falls:
        for y in range(top, bottom + 1):
            # Gentle deterministic wobble as the water falls.
            wob = int(4 * ((y * 7) % 11 - 5) / 5)
            x0 = fx + wob
            fade = 1.0 - 0.35 * (y - top) / max(1, bottom - top)
            for x in range(x0, x0 + wdt):
                # Streaky: alternate brighter / dimmer columns.
                bright = 235 if (x + y) % 3 else 200
                blend_px(x, y, bright, 225, 200, 0.55 * fade)
        # Mist puff where the fall meets the sea.
        ellipse_alpha(fx + wdt // 2, bottom + 6, 34, 12, 255, 226, 190, 0.30)


# ---------------------------------------------------------------- sea glitter
def paint_glitter():
    for y in range(HORIZON + 4, H, 1):
        depth = (y - HORIZON) / (H - HORIZON)
        width = 230 * (1.0 - 0.55 * depth)
        for x in range(max(0, int(SUN_X - width)), min(W, int(SUN_X + width))):
            fall = 1.0 - abs(x - SUN_X) / width
            h = hash2(x, y // 2)
            # Sparse sparkles, denser near the horizon.
            if (h % 100) < int(28 * fall * (1.0 - 0.6 * depth)):
                a = 0.35 + 0.35 * ((h >> 8) % 10) / 10.0
                blend_px(x, y, 255, 214, 150, a * fall)


# ---------------------------------------------------------------- birds
def paint_birds():
    birds = [(300, 282, 9), (342, 302, 7), (560, 242, 8),
             (604, 266, 6), (382, 332, 7), (648, 300, 6)]
    for (bx, by, s) in birds:
        for i in range(s):
            set_px(bx - s + i, by + i // 2, 52, 28, 58)
            set_px(bx + i, by + i // 2, 52, 28, 58)


# ---------------------------------------------------------------- lettering
# 5x7 bitmap font, drawn from data written for this poster.
FONT = {
    'A': ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    'B': ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    'C': ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    'D': ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    'E': ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    'F': ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    'G': ["01110", "10001", "10000", "10111", "10001", "10001", "01111"],
    'H': ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    'I': ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    'J': ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    'K': ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    'L': ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    'M': ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    'N': ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    'O': ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    'P': ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    'Q': ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    'R': ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    'S': ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    'T': ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    'U': ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    'V': ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    'W': ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
    'X': ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    'Y': ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    'Z': ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    ' ': ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
}


def text_width(text, scale, spacing):
    return len(text) * 5 * scale + max(0, len(text) - 1) * spacing


def draw_text(text, x0, y0, scale, spacing, r, g, b, alpha=1.0):
    """Draw text with the bitmap font; x0 is the left edge, y0 the top."""
    x = x0
    for ch in text:
        glyph = FONT.get(ch, FONT[' '])
        for gy in range(7):
            row_bits = glyph[gy]
            for gx in range(5):
                if row_bits[gx] == '1':
                    px0 = x + gx * scale
                    py0 = y0 + gy * scale
                    if alpha >= 1.0:
                        fill_rect(px0, py0, px0 + scale, py0 + scale, r, g, b)
                    else:
                        for yy in range(py0, py0 + scale):
                            for xx in range(px0, px0 + scale):
                                blend_px(xx, yy, r, g, b, alpha)
        x += 5 * scale + spacing


def paint_name():
    name = "VELMARA"
    sub = "THE LOW SUN ISLES"
    scale = 13
    spacing = 26
    wdt = text_width(name, scale, spacing)
    x0 = (W - wdt) // 2
    y0 = 108
    # Soft dark band behind the lockup for legibility against the sky.
    ellipse_alpha(W // 2, y0 + 45, 380, 78, 40, 18, 64, 0.30)
    # Shadow + outline, then the cream face.
    draw_text(name, x0 + 7, y0 + 9, scale, spacing, *NAME_SHADOW, alpha=0.55)
    for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3)):
        draw_text(name, x0 + dx, y0 + dy, scale, spacing, 52, 24, 66,
                  alpha=0.6)
    draw_text(name, x0, y0, scale, spacing, *NAME_CREAM)
    # Small region line under the name, part of the lockup.
    s2, sp2 = 4, 10
    w2 = text_width(sub, s2, sp2)
    draw_text(sub, (W - w2) // 2, y0 + 7 * scale + 18, s2, sp2,
              255, 226, 190, alpha=0.95)


# ---------------------------------------------------------------- grain
def paint_grain():
    # Deterministic ±2 grain so gradients do not band; same offset per pixel
    # across channels keeps the hue intact.
    for y in range(H):
        row = img[y]
        for x in range(W):
            g = (hash2(x, y) % 5) - 2
            if g:
                o = x * 3
                row[o] = clamp255(row[o] + g)
                row[o + 1] = clamp255(row[o + 1] + g)
                row[o + 2] = clamp255(row[o + 2] + g)


# ---------------------------------------------------------------- PNG out
def write_png(path, rows, w, h):
    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        out += struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return out

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(row) for row in rows)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


def main():
    paint_base()
    paint_clouds()
    paint_sun()
    paint_islands()
    paint_waterfalls()
    paint_glitter()
    paint_birds()
    paint_name()
    paint_grain()
    os.makedirs("/output", exist_ok=True)
    size = write_png("/output/entry.png", img, W, H)
    print(f"wrote /output/entry.png {W}x{H} {size} bytes")


if __name__ == "__main__":
    main()
