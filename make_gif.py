#!/usr/bin/env python3
"""
Render PRIMORDEA as an animated GIF.

Usage:  python3 make_gif.py [--ticks N] [--frames F] [--out FILE]

Defaults: 800 ticks → 200 frames  (4 ticks per frame)
"""
import sys, os, argparse, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'primordea'))

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from world import World
from config import WORLD_W, WORLD_H

# ── Visual constants ──────────────────────────────────────────────────────────
CELL   = 9                          # px per simulation cell
BG     = (4, 6, 15)
HEADER = 28                         # px tall stats bar at top
IMG_W  = WORLD_W * CELL             # 900
IMG_H  = WORLD_H * CELL + HEADER    # 324 + 28 = 352

# 12 species colours (RGB)
SP_COL = [
    (0,  229, 255),   # cyan
    (255,  82,  82),  # red
    (255, 229,   0),  # yellow
    (234,  64, 251),  # magenta
    ( 68, 138, 255),  # blue
    (105, 255, 154),  # green
    (235, 235, 235),  # white
    (255, 110,   0),  # orange
    (240,  98, 146),  # pink
    (128, 222, 234),  # teal
    (206, 147, 216),  # lavender
    (165, 214, 167),  # sage
]
SP_SYMS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

# ── Load font (graceful fallback) ─────────────────────────────────────────────
def _load_font(size):
    for path in [
        '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf',
        '/usr/share/fonts/truetype/freefont/FreeMono.ttf',
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()

FONT_SM = _load_font(10)
FONT_MD = _load_font(12)

# ── Food colour ───────────────────────────────────────────────────────────────
def food_rgb(v: float):
    if v <= 0:
        return BG
    t = min(v / 3.0, 1.0) ** 0.55       # gamma for perceptual spread
    return (int(4 + t*30), int(6 + t*210), int(15 + t*45))

# Precompute food colour lookup (0-255 quantised value → RGB)
_FOOD_LUT = [food_rgb(i / 255 * 3.0) for i in range(256)]

# ── Single frame renderer ─────────────────────────────────────────────────────
def render_frame(world: World) -> Image.Image:
    # Build world pixel array via numpy (fast path)
    arr = np.full((WORLD_H * CELL, WORLD_W * CELL, 3), BG, dtype=np.uint8)

    # Food
    food_q = (world.food * (255.0 / 3.0)).clip(0, 255).astype(np.uint8)
    for y in range(WORLD_H):
        for x in range(WORLD_W):
            fv = food_q[y, x]
            if fv > 2:
                r, g, b = _FOOD_LUT[fv]
                py0, px0 = y * CELL, x * CELL
                arr[py0:py0+CELL, px0:px0+CELL] = (r, g, b)

    img  = Image.fromarray(arr, 'RGB')
    draw = ImageDraw.Draw(img)

    # Organisms
    org_at = {}
    for o in world.organisms:
        key = (o.y, o.x)
        if key not in org_at:
            org_at[key] = o

    for (oy, ox), o in org_at.items():
        cx = ox * CELL + CELL // 2
        cy = oy * CELL + CELL // 2
        r  = max(2, int(CELL * 0.38 * (0.55 + o.energy / 200.0 * 0.75)))
        c  = SP_COL[o.species % 12]

        # Glow halo
        gc = (c[0]//4, c[1]//4, c[2]//4)
        draw.ellipse([cx-r-3, cy-r-3, cx+r+3, cy+r+3], fill=gc)

        # Body
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=c)

        # Bright core
        cr = max(1, r//3)
        core = tuple(min(255, v + 100) for v in c)
        draw.ellipse([cx-cr, cy-cr, cx+cr, cy+cr], fill=core)

    return img


def build_header(world: World, img_w: int) -> Image.Image:
    hdr  = Image.new('RGB', (img_w, HEADER), (7, 11, 24))
    draw = ImageDraw.Draw(hdr)
    sp   = world.count_species()
    snap = world.stats_snapshot()

    # Separator line
    draw.line([(0, HEADER-1), (img_w-1, HEADER-1)], fill=(0, 60, 40))

    ACCENT = (0, 210, 130)
    DIM    = (60, 100, 80)
    WHITE  = (185, 215, 210)

    # Title
    draw.text((8, 6), 'PRIMORDEA', fill=ACCENT, font=FONT_MD)

    # Stats
    parts = [
        (f'tick {world.tick:>6}',          WHITE),
        (f'pop {len(world.organisms):>4}',  (80, 200, 255)),
        (f'species {len(sp):>2}',           (200, 200, 80)),
        (f'gen {snap.get("max_gen",0):>3}', (180, 180, 180)),
        (f'born {world.total_born:>5}',     (80, 200, 100)),
        (f'extinct {world.extinctions:>2}', DIM),
    ]
    x = 110
    for txt, col in parts:
        draw.text((x, 7), txt, fill=col, font=FONT_SM)
        x += len(txt) * 7 + 8

    # Mini species swatches
    sx = img_w - 10
    for sp_id, cnt in sorted(sp.items(), key=lambda kv: -kv[1])[:12]:
        c = SP_COL[sp_id % 12]
        sx -= 12
        draw.rectangle([sx, 8, sx+9, 19], fill=c)

    return hdr


def composite(world_img: Image.Image, world: World) -> Image.Image:
    out  = Image.new('RGB', (IMG_W, IMG_H), BG)
    hdr  = build_header(world, IMG_W)
    out.paste(hdr, (0, 0))
    out.paste(world_img, (0, HEADER))
    return out


# ── Main ──────────────────────────────────────────────────────────────────────
def run(total_ticks=800, n_frames=200, output='primordea.gif', fps=20):
    world = World()
    tpf   = max(1, total_ticks // n_frames)  # ticks per frame

    print(f'\n  PRIMORDEA GIF generator')
    print(f'  {total_ticks} ticks → {n_frames} frames  ({tpf} ticks/frame)')
    print(f'  Output: {output}  ({IMG_W}×{IMG_H} px, {fps} FPS)\n')

    frames = []
    t0 = time.time()

    for i in range(n_frames):
        for _ in range(tpf):
            world.step()

        world_img = render_frame(world)
        frame     = composite(world_img, world)
        frames.append(frame)

        if (i + 1) % 40 == 0 or i == n_frames - 1:
            elapsed  = time.time() - t0
            eta      = elapsed / (i + 1) * (n_frames - i - 1)
            sp       = world.count_species()
            print(f'  [{i+1:>3}/{n_frames}]  tick={world.tick:>5}  '
                  f'pop={len(world.organisms):>4}  '
                  f'species={len(sp):>3}  '
                  f'ETA {eta:.0f}s')

    print(f'\n  Saving {output} ...')
    frames[0].save(
        output,
        save_all       = True,
        append_images  = frames[1:],
        loop           = 0,            # loop forever
        duration       = 1000 // fps,  # ms per frame
        optimize       = True,
    )
    kb = os.path.getsize(output) / 1024
    print(f'  Done!  {kb:.0f} KB\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--ticks',  type=int, default=800)
    p.add_argument('--frames', type=int, default=200)
    p.add_argument('--out',    default='primordea.gif')
    p.add_argument('--fps',    type=int, default=20)
    a = p.parse_args()
    run(a.ticks, a.frames, a.out, a.fps)
