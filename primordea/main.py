"""
PRIMORDEA — Digital Evolution Simulator
========================================
Neural-brained organisms evolve in a toroidal world with regenerating food.
Each organism has a feedforward neural network brain; evolution acts on
network weights through mutation and sexual recombination.

Controls
--------
  [p]   Pause / Resume
  [f]   Food burst (rain food on the world)
  [r]   Inject 15 new random organisms
  [+]   Double simulation speed
  [-]   Halve simulation speed
  [q]   Quit
"""

import curses
import time
import sys
import os

# Allow running from the primordea/ directory or from parent
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from world import World
from config import WORLD_W, WORLD_H, HISTORY_LEN, SPECIES_COLOR_IDS, SPECIES_SYMS, FPS


# ─────────────────────────────────────────────────────────────────────────────
#  Colour setup
# ─────────────────────────────────────────────────────────────────────────────

# curses color constants
_C = [
    curses.COLOR_BLACK,   # 0
    curses.COLOR_RED,     # 1
    curses.COLOR_GREEN,   # 2
    curses.COLOR_YELLOW,  # 3
    curses.COLOR_BLUE,    # 4
    curses.COLOR_MAGENTA, # 5
    curses.COLOR_CYAN,    # 6
    curses.COLOR_WHITE,   # 7
]

CP_FOOD_LO  = 1
CP_FOOD_MED = 2
CP_FOOD_HI  = 3
CP_HEADER   = 4
CP_STAT     = 5
CP_DIM      = 6
CP_ACCENT   = 7
CP_SP_BASE  = 20   # species i uses pair CP_SP_BASE + (i % N_SPECIES_COLORS)
N_SP_COLORS = len(SPECIES_COLOR_IDS)


def init_colors():
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except Exception:
        bg = curses.COLOR_BLACK

    curses.init_pair(CP_FOOD_LO,  curses.COLOR_GREEN,  bg)
    curses.init_pair(CP_FOOD_MED, curses.COLOR_GREEN,  bg)
    curses.init_pair(CP_FOOD_HI,  curses.COLOR_GREEN,  bg)
    curses.init_pair(CP_HEADER,   curses.COLOR_CYAN,   bg)
    curses.init_pair(CP_STAT,     curses.COLOR_WHITE,  bg)
    curses.init_pair(CP_DIM,      curses.COLOR_WHITE,  bg)
    curses.init_pair(CP_ACCENT,   curses.COLOR_YELLOW, bg)

    for i, col_id in enumerate(SPECIES_COLOR_IDS):
        curses.init_pair(CP_SP_BASE + i, _C[col_id], bg)


# ─────────────────────────────────────────────────────────────────────────────
#  Rendering helpers
# ─────────────────────────────────────────────────────────────────────────────

SPARKLINE_BARS = " ▁▂▃▄▅▆▇█"

def sparkline(values: list, width: int, max_val: float = None) -> str:
    if not values:
        return " " * width
    mv = max_val or (max(values) or 1)
    seg = values[-width:]
    return "".join(SPARKLINE_BARS[min(int(v / mv * 8), 8)] for v in seg)


def safe_addstr(win, y: int, x: int, s: str, attr: int = 0):
    h, w = win.getmaxyx()
    if y < 0 or y >= h - 1:
        return
    avail = w - x - 1
    if avail <= 0:
        return
    try:
        win.addstr(y, x, s[:avail], attr)
    except curses.error:
        pass


def safe_addch(win, y: int, x: int, ch: str, attr: int = 0):
    h, w = win.getmaxyx()
    if y < 0 or y >= h - 1 or x < 0 or x >= w - 1:
        return
    try:
        win.addch(y, x, ch, attr)
    except curses.error:
        pass


# ─────────────────────────────────────────────────────────────────────────────
#  World renderer
# ─────────────────────────────────────────────────────────────────────────────

def render_world(win, world: World, wy: int, wx: int, wh: int, ww: int):
    """Paint the simulation grid onto the window."""
    # Build a (y, x) -> Organism lookup (first organism wins for display)
    org_at: dict[tuple[int,int], object] = {}
    for o in world.organisms:
        key = (o.y, o.x)
        if key not in org_at:
            org_at[key] = o

    for y in range(min(wh, WORLD_H)):
        for x in range(min(ww, WORLD_W)):
            sy, sx = wy + y, wx + x
            key = (y, x)
            if key in org_at:
                o   = org_at[key]
                cp  = curses.color_pair(CP_SP_BASE + (o.species % N_SP_COLORS))
                sym = SPECIES_SYMS[o.species % len(SPECIES_SYMS)]
                safe_addch(win, sy, sx, sym, cp | curses.A_BOLD)
            else:
                food = world.food[y, x]
                if food <= 0:
                    safe_addch(win, sy, sx, ' ')
                elif food < 1.0:
                    safe_addch(win, sy, sx, '.', curses.color_pair(CP_FOOD_LO) | curses.A_DIM)
                elif food < 2.0:
                    safe_addch(win, sy, sx, ':', curses.color_pair(CP_FOOD_MED))
                else:
                    safe_addch(win, sy, sx, '+', curses.color_pair(CP_FOOD_HI) | curses.A_BOLD)


def render_stats(win, world: World, sy0: int, sx0: int, sh: int, sw: int,
                 paused: bool, speed: int):
    """Paint the statistics sidebar."""
    row = 0

    def put(text, attr=0, indent=0):
        nonlocal row
        safe_addstr(win, sy0 + row, sx0 + indent, text, attr)
        row += 1

    header = curses.color_pair(CP_HEADER) | curses.A_BOLD
    stat   = curses.color_pair(CP_STAT)
    dim    = curses.A_DIM
    accent = curses.color_pair(CP_ACCENT)

    # Title
    title = "PRIMORDEA"
    safe_addstr(win, sy0 + row, sx0 + (sw - len(title)) // 2, title, header)
    row += 1
    put("─" * sw, dim)

    # Status
    status_str = f"PAUSED" if paused else f"x{speed:>2} speed"
    put(f"Tick  {world.tick:>8}  [{status_str}]", stat)

    stats = world.stats_snapshot()
    pop = len(world.organisms)

    put(f"Pop   {pop:>8}", stat)
    put(f"Born  {world.total_born:>8}", curses.color_pair(CP_FOOD_HI))
    put(f"Died  {world.total_died:>8}", curses.color_pair(1) | curses.A_DIM)
    put(f"Extct {world.extinctions:>8}", dim)

    if stats:
        put("─" * sw, dim)
        put(f"MaxGen {stats['max_gen']:>7}", accent)
        put(f"AvgAge {stats['avg_age']:>7.1f}", accent)
        put(f"MaxAge {stats['max_age']:>7}", accent)
        put(f"MaxKids{stats['max_kids']:>7}", accent)
        put(f"AvgNrg {stats['avg_energy']:>7.1f}", accent)

    # Species table
    put("─" * sw, dim)
    sp_counts = world.count_species()
    n_sp = len(sp_counts)
    put(f"Species: {n_sp}", header)

    max_count = max(sp_counts.values(), default=1)
    bar_w = max(sw - 10, 2)
    for sp_id, count in sorted(sp_counts.items(), key=lambda kv: -kv[1])[:10]:
        if sy0 + row >= sh - 6:
            break
        cp  = curses.color_pair(CP_SP_BASE + (sp_id % N_SP_COLORS)) | curses.A_BOLD
        sym = SPECIES_SYMS[sp_id % len(SPECIES_SYMS)]
        bar = int(count / max_count * bar_w)
        safe_addstr(win, sy0 + row, sx0, f"[{sym}]{count:>4} ", cp)
        safe_addstr(win, sy0 + row, sx0 + 8, "█" * bar,
                    curses.color_pair(CP_SP_BASE + (sp_id % N_SP_COLORS)))
        row += 1

    # Sparklines
    spark_w = sw - 2
    put("─" * sw, dim)
    put("Population", curses.color_pair(CP_STAT) | curses.A_BOLD)
    put(sparkline(world.pop_history, spark_w), curses.color_pair(CP_HEADER))

    put("Food supply", curses.color_pair(CP_STAT) | curses.A_BOLD)
    fmax = WORLD_W * WORLD_H * 3.0
    put(sparkline(world.food_history, spark_w, fmax), curses.color_pair(CP_FOOD_HI))

    put("Diversity", curses.color_pair(CP_STAT) | curses.A_BOLD)
    put(sparkline(world.div_history, spark_w), accent)

    # Recent speciation events
    if world.events:
        put("─" * sw, dim)
        put("Events", curses.color_pair(CP_STAT) | curses.A_BOLD)
        for evt in world.events[-4:]:
            if sy0 + row >= sh - 3:
                break
            put(evt[:sw], accent | curses.A_DIM)

    # Controls hint
    safe_addstr(win, sh - 2, sx0, "[p]ause [f]ood [r]inject [+/-]spd [q]uit", dim)


def render_border(win, wy: int, ww: int):
    """Vertical separator between world and stats."""
    h = win.getmaxyx()[0]
    for y in range(1, h - 1):
        safe_addch(win, y, ww, '│', curses.A_DIM)


# ─────────────────────────────────────────────────────────────────────────────
#  Splash screen
# ─────────────────────────────────────────────────────────────────────────────

SPLASH = r"""
  ██████╗ ██████╗ ██╗███╗   ███╗ ██████╗ ██████╗ ██████╗ ███████╗ █████╗
  ██╔══██╗██╔══██╗██║████╗ ████║██╔═══██╗██╔══██╗██╔══██╗██╔════╝██╔══██╗
  ██████╔╝██████╔╝██║██╔████╔██║██║   ██║██████╔╝██║  ██║█████╗  ███████║
  ██╔═══╝ ██╔══██╗██║██║╚██╔╝██║██║   ██║██╔══██╗██║  ██║██╔══╝  ██╔══██║
  ██║     ██║  ██║██║██║ ╚═╝ ██║╚██████╔╝██║  ██║██████╔╝███████╗██║  ██║
  ╚═╝     ╚═╝  ╚═╝╚═╝╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚══════╝╚═╝  ╚═╝
                     Digital Evolution Simulator
         Neural-brained organisms competing, evolving, speciating.
              Press any key to begin the primordial soup...
"""

def show_splash(stdscr):
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    lines = SPLASH.strip("\n").split("\n")
    start_y = max(0, (h - len(lines)) // 2)
    for i, line in enumerate(lines):
        x = max(0, (w - len(line)) // 2)
        try:
            attr = curses.color_pair(CP_HEADER) | curses.A_BOLD
            stdscr.addstr(start_y + i, x, line[:w-1], attr)
        except curses.error:
            pass
    stdscr.refresh()
    stdscr.nodelay(False)
    stdscr.getch()
    stdscr.nodelay(True)


# ─────────────────────────────────────────────────────────────────────────────
#  Main simulation loop
# ─────────────────────────────────────────────────────────────────────────────

def run(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)
    init_colors()

    show_splash(stdscr)

    world  = World()
    paused = False
    speed  = 1

    STATS_W = 36

    while True:
        # ── Input ──────────────────────────────────────────────────────
        key = stdscr.getch()
        if key in (ord('q'), ord('Q'), 27):          # q / Esc
            break
        elif key in (ord('p'), ord('P'), ord(' ')):
            paused = not paused
        elif key == ord('f'):
            world.add_food_burst()
        elif key == ord('r'):
            world.inject_organisms(15)
        elif key in (ord('+'), ord('=')):
            speed = min(speed * 2, 32)
        elif key == ord('-'):
            speed = max(1, speed // 2)
        elif key == curses.KEY_RESIZE:
            stdscr.clear()

        # ── Simulate ───────────────────────────────────────────────────
        if not paused:
            for _ in range(speed):
                world.step()

        # ── Render ─────────────────────────────────────────────────────
        scr_h, scr_w = stdscr.getmaxyx()

        world_w = min(WORLD_W, scr_w - STATS_W - 2)
        world_h = min(WORLD_H, scr_h - 2)

        stdscr.erase()

        # Title bar
        title = f" PRIMORDEA  tick:{world.tick}  pop:{len(world.organisms)} "
        tx = max(0, (scr_w - len(title)) // 2)
        safe_addstr(stdscr, 0, tx, title,
                    curses.color_pair(CP_HEADER) | curses.A_BOLD | curses.A_REVERSE)

        # World grid
        render_world(stdscr, world, 1, 0, world_h, world_w)

        # Separator
        render_border(stdscr, 1, world_w)

        # Stats panel
        if scr_w > world_w + 2:
            render_stats(stdscr, world, 1, world_w + 1, scr_h, STATS_W,
                         paused, speed)

        stdscr.refresh()
        time.sleep(1.0 / FPS)


def main():
    try:
        curses.wrapper(run)
    except KeyboardInterrupt:
        pass
    print("\nPrimordea terminated.")


if __name__ == "__main__":
    main()
