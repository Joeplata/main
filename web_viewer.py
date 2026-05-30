#!/usr/bin/env python3
"""
PRIMORDEA — Web Visualizer
Run:  python3 web_viewer.py
Then open the printed URL in your browser.
"""

import sys, os, threading, time, json

ROOT  = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, 'primordea'))

from flask import Flask, Response, request
from world import World
from config import WORLD_W, WORLD_H

app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# ── Simulation state ──────────────────────────────────────────────────────────
_lock   = threading.Lock()
_world  = World()
_paused = False
_speed  = 1     # world.step() calls per background tick

def _sim_loop():
    while True:
        if not _paused:
            with _lock:
                for _ in range(_speed):
                    _world.step()
        time.sleep(1.0 / 60)

threading.Thread(target=_sim_loop, daemon=True).start()

# ── API ───────────────────────────────────────────────────────────────────────

@app.route('/api/state')
def api_state():
    with _lock:
        food_q = (_world.food * (255.0 / 3.0)).clip(0, 255).astype('uint8').flatten().tolist()
        orgs   = [
            {'x': int(o.x), 'y': int(o.y),
             'sp': int(o.species % 12),
             'e':  round(float(o.energy / 200.0), 2)}
            for o in _world.organisms
        ]
        sp_raw   = _world.count_species()
        sp_out   = {str(k): v for k, v in sorted(sp_raw.items(), key=lambda x: -x[1])[:15]}
        snap     = _world.stats_snapshot()
        # Convert any numpy scalars to native Python types
        snap_clean = {k: (float(v) if hasattr(v, 'item') else v)
                      for k, v in snap.items()} if snap else {}
        payload  = {
            'tick':       int(_world.tick),
            'pop':        len(_world.organisms),
            'born':       int(_world.total_born),
            'died':       int(_world.total_died),
            'ext':        int(_world.extinctions),
            'food':       food_q,
            'organisms':  orgs,
            'species':    sp_out,
            'pop_hist':   _world.pop_history[-80:],
            'div_hist':   _world.div_history[-80:],
            'events':     list(_world.events[-6:]),
            'stats':      snap_clean,
            'paused':     bool(_paused),
            'speed':      int(_speed),
        }
    resp = Response(json.dumps(payload), mimetype='application/json')
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/api/control', methods=['POST'])
def api_control():
    global _paused, _speed, _world
    cmd = (request.json or {}).get('cmd', '')
    if   cmd == 'pause':      _paused = not _paused
    elif cmd == 'food':
        with _lock: _world.add_food_burst()
    elif cmd == 'inject':
        with _lock: _world.inject_organisms(15)
    elif cmd == 'speed_up':   _speed = min(_speed * 2, 64)
    elif cmd == 'speed_down': _speed = max(1, _speed // 2)
    elif cmd == 'reset':
        with _lock:
            _world  = World()
            _paused = False
            _speed  = 1
    return Response(
        json.dumps({'ok': True, 'paused': _paused, 'speed': _speed}),
        mimetype='application/json'
    )


@app.route('/')
def index():
    return HTML


# ── Embedded frontend ─────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PRIMORDEA — Digital Evolution</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:      #04060f;
  --panel:   #070b18;
  --border:  rgba(0,220,140,0.12);
  --accent:  #00ffaa;
  --muted:   #3a5c70;
  --text:    #8ab8cc;
  --bright:  #c8e8f8;
}

body {
  background: var(--bg);
  color: var(--text);
  font-family: 'Consolas','Menlo','Monaco',monospace;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── Header ── */
#hdr {
  height: 42px;
  background: rgba(0,255,170,0.04);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 0;
  padding: 0 16px;
  flex-shrink: 0;
}
#hdr h1 {
  font-size: 15px;
  letter-spacing: 5px;
  color: var(--accent);
  margin-right: 24px;
  text-shadow: 0 0 12px rgba(0,255,170,0.5);
}
.hstat { margin-right: 18px; font-size: 12px; color: var(--muted); }
.hstat span { color: var(--accent); font-weight: bold; }
#speed-badge {
  margin-left: auto;
  font-size: 11px;
  background: rgba(0,255,170,0.1);
  border: 1px solid rgba(0,255,170,0.25);
  color: var(--accent);
  padding: 2px 8px;
  border-radius: 3px;
  letter-spacing: 1px;
}

/* ── Main layout ── */
#main {
  display: flex;
  flex: 1;
  min-height: 0;
}

/* ── World canvas stack ── */
#world-wrap {
  flex: 1;
  position: relative;
  background: #04060f;
  min-width: 0;
}
#world-wrap canvas {
  position: absolute;
  top: 0; left: 0;
  width: 100%;
  height: 100%;
}
#food-canvas { z-index: 1; filter: blur(1.5px) brightness(1.1); }
#org-canvas  { z-index: 2; }

/* ── Sidebar ── */
#side {
  width: 290px;
  flex-shrink: 0;
  background: var(--panel);
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
#side-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 10px 12px 80px;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

.sec { font-size: 10px; letter-spacing: 2.5px; color: var(--accent);
       text-transform: uppercase; margin: 14px 0 5px;
       border-bottom: 1px solid var(--border); padding-bottom: 3px; }

.row { display: flex; justify-content: space-between; font-size: 12px;
       padding: 2px 0; color: var(--muted); }
.row span:last-child { color: var(--bright); }

/* ── Controls ── */
#ctrls {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin: 6px 0 2px;
}
.btn {
  padding: 4px 9px;
  font-size: 11px;
  font-family: inherit;
  background: rgba(0,255,170,0.07);
  border: 1px solid rgba(0,255,170,0.22);
  color: var(--accent);
  cursor: pointer;
  border-radius: 3px;
  letter-spacing: 0.5px;
  transition: background 0.15s;
}
.btn:hover   { background: rgba(0,255,170,0.18); }
.btn.pressed { background: rgba(0,255,170,0.30); }

/* ── Species bars ── */
.sp-row {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 2px 0;
  font-size: 11px;
}
.sp-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.sp-name { width: 18px; color: var(--muted); flex-shrink: 0; }
.sp-bar-bg { flex: 1; height: 5px; background: rgba(255,255,255,0.05);
             border-radius: 3px; overflow: hidden; }
.sp-bar    { height: 100%; border-radius: 3px; transition: width 0.4s ease; }
.sp-cnt    { font-size: 11px; color: var(--bright); min-width: 26px; text-align: right; }

/* ── Graphs ── */
.graph-wrap { margin: 4px 0; border: 1px solid var(--border); border-radius: 3px;
              background: rgba(0,0,0,0.3); }
.graph-label { font-size: 9px; color: var(--muted); padding: 2px 4px; letter-spacing: 1px; }
.graph-wrap canvas { width: 100%; display: block; }

/* ── Events ── */
#events { font-size: 10px; line-height: 1.9; color: var(--muted); }
.evt-line { color: rgba(0,220,140,0.55); }

/* ── Footer controls pinned ── */
#footer-ctrls {
  padding: 8px 12px;
  border-top: 1px solid var(--border);
  background: var(--panel);
  flex-shrink: 0;
}
</style>
</head>
<body>

<!-- Header -->
<div id="hdr">
  <h1>PRIMORDEA</h1>
  <div class="hstat">tick <span id="h-tick">0</span></div>
  <div class="hstat">pop <span id="h-pop">0</span></div>
  <div class="hstat">species <span id="h-sp">0</span></div>
  <div class="hstat">gen <span id="h-gen">0</span></div>
  <div id="speed-badge" id="h-spd">×1</div>
</div>

<!-- Main -->
<div id="main">

  <!-- World canvas (food layer + organism layer) -->
  <div id="world-wrap">
    <canvas id="food-canvas"></canvas>
    <canvas id="org-canvas"></canvas>
  </div>

  <!-- Sidebar -->
  <div id="side">
    <div id="side-scroll">

      <div class="sec">Stats</div>
      <div class="row"><span>Born</span>   <span id="s-born">0</span></div>
      <div class="row"><span>Died</span>   <span id="s-died">0</span></div>
      <div class="row"><span>Extinct</span><span id="s-ext">0</span></div>
      <div class="row"><span>Max Gen</span><span id="s-mgen">0</span></div>
      <div class="row"><span>Avg Age</span><span id="s-aage">0</span></div>
      <div class="row"><span>Avg Energy</span><span id="s-anrg">0</span></div>
      <div class="row"><span>Max Kids</span><span id="s-mkid">0</span></div>

      <div class="sec">Population</div>
      <div class="graph-wrap">
        <div class="graph-label">▲ organisms alive</div>
        <canvas id="pop-graph" height="64"></canvas>
      </div>

      <div class="sec">Diversity</div>
      <div class="graph-wrap">
        <div class="graph-label">▲ species count</div>
        <canvas id="div-graph" height="40"></canvas>
      </div>

      <div class="sec">Species</div>
      <div id="sp-list"></div>

      <div class="sec">Events</div>
      <div id="events"><span style="color:var(--muted)">Waiting for speciation…</span></div>

    </div>

    <!-- Pinned controls -->
    <div id="footer-ctrls">
      <div id="ctrls">
        <button class="btn" id="btn-pause"  onclick="ctrl('pause')">⏸ Pause</button>
        <button class="btn" onclick="ctrl('food')">🌿 Food</button>
        <button class="btn" onclick="ctrl('inject')">✦ Inject</button>
        <button class="btn" onclick="ctrl('speed_up')">⏩+</button>
        <button class="btn" onclick="ctrl('speed_down')">⏪−</button>
        <button class="btn" onclick="ctrl('reset')">↺ Reset</button>
      </div>
    </div>
  </div>

</div>

<script>
'use strict';

// ── World constants ──────────────────────────────────────────────────────────
const WW = 100, WH = 36;

// Species palette: 12 vivid colors matching curses config
const SP_COLORS = [
  '#00e5ff', // 0 cyan
  '#ff5252', // 1 red
  '#ffe500', // 2 yellow
  '#ea40fb', // 3 magenta
  '#448aff', // 4 blue
  '#69ff9a', // 5 green
  '#f5f5f5', // 6 white
  '#ff6e00', // 7 orange
  '#f06292', // 8 pink
  '#80deea', // 9 teal
  '#ce93d8', // 10 lavender
  '#a5d6a7', // 11 sage
];
const SP_SYMS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';

// ── Canvas setup ─────────────────────────────────────────────────────────────
const foodCanvas = document.getElementById('food-canvas');
const orgCanvas  = document.getElementById('org-canvas');
const foodCtx    = foodCanvas.getContext('2d');
const ctx        = orgCanvas.getContext('2d');

// Off-screen food buffer at world resolution
const foodBuf    = document.createElement('canvas');
foodBuf.width    = WW;
foodBuf.height   = WH;
const foodBufCtx = foodBuf.getContext('2d');
const foodImg    = foodBufCtx.createImageData(WW, WH);

// Pre-render species glyphs into small canvases (drawn with drawImage → fast)
const GLYPHS = [];
const GLYPH_SZ = 32;
for (let sp = 0; sp < 12; sp++) {
  const gc = document.createElement('canvas');
  gc.width = gc.height = GLYPH_SZ;
  const gx = gc.getContext('2d');
  const c  = SP_COLORS[sp];

  // Outer glow
  gx.shadowBlur = GLYPH_SZ * 0.55;
  gx.shadowColor = c;
  gx.fillStyle = c;
  gx.globalAlpha = 0.7;
  gx.beginPath();
  gx.arc(GLYPH_SZ/2, GLYPH_SZ/2, GLYPH_SZ * 0.30, 0, Math.PI * 2);
  gx.fill();

  // Core bright
  gx.shadowBlur = GLYPH_SZ * 0.2;
  gx.globalAlpha = 1.0;
  gx.fillStyle = '#ffffff';
  gx.beginPath();
  gx.arc(GLYPH_SZ/2, GLYPH_SZ/2, GLYPH_SZ * 0.13, 0, Math.PI * 2);
  gx.fill();

  GLYPHS.push(gc);
}

function resizeCanvases() {
  const wrap = document.getElementById('world-wrap');
  const w = wrap.clientWidth, h = wrap.clientHeight;
  [foodCanvas, orgCanvas].forEach(c => { c.width = w; c.height = h; });
}
resizeCanvases();
window.addEventListener('resize', () => { resizeCanvases(); });

// ── Food rendering ────────────────────────────────────────────────────────────
function renderFood(food) {
  const d = foodImg.data;
  for (let i = 0; i < WW * WH; i++) {
    const v  = food[i] / 255;          // 0..1
    const t  = Math.pow(v, 0.55);      // gamma for perceptual spread
    const p  = i * 4;
    if (v < 0.005) {
      d[p]=4; d[p+1]=6; d[p+2]=15; d[p+3]=255;   // background
    } else {
      d[p]   = Math.round(t * 28);                 // R
      d[p+1] = Math.round(8 + t * 210);            // G — dominant
      d[p+2] = Math.round(15 + t * 45);            // B
      d[p+3] = 255;
    }
  }
  foodBufCtx.putImageData(foodImg, 0, 0);

  // Scale up to display canvas
  const w = foodCanvas.width, h = foodCanvas.height;
  foodCtx.clearRect(0, 0, w, h);
  foodCtx.imageSmoothingEnabled = true;
  foodCtx.imageSmoothingQuality = 'medium';
  foodCtx.drawImage(foodBuf, 0, 0, w, h);
}

// ── Organism rendering ────────────────────────────────────────────────────────
function renderOrgs(organisms) {
  const w = orgCanvas.width, h = orgCanvas.height;
  ctx.clearRect(0, 0, w, h);

  const CW = w / WW, CH = h / WH;
  const BASE_R = Math.min(CW, CH) * 0.38;

  for (const o of organisms) {
    const cx = (o.x + 0.5) * CW;
    const cy = (o.y + 0.5) * CH;
    const r  = BASE_R * (0.55 + o.e * 0.75);
    const sz = r * 2.4;               // glyph draw size
    ctx.drawImage(GLYPHS[o.sp], cx - sz/2, cy - sz/2, sz, sz);
  }
}

// ── Graph rendering ───────────────────────────────────────────────────────────
function drawGraph(canvasId, data, color, maxOverride) {
  const c  = document.getElementById(canvasId);
  const gx = c.getContext('2d');
  const w  = c.clientWidth || c.width;
  const h  = c.height;
  c.width  = w;   // force pixel sync with CSS width

  gx.clearRect(0, 0, w, h);
  if (!data || data.length < 2) return;

  const mx = maxOverride || (Math.max(...data) || 1);
  const pad = 4;
  const eff_h = h - pad * 2;

  gx.beginPath();
  for (let i = 0; i < data.length; i++) {
    const x = (i / (data.length - 1)) * w;
    const y = pad + eff_h - (data[i] / mx) * eff_h;
    i === 0 ? gx.moveTo(x, y) : gx.lineTo(x, y);
  }

  gx.strokeStyle = color;
  gx.lineWidth = 1.5;
  gx.shadowBlur = 4;
  gx.shadowColor = color;
  gx.stroke();
  gx.shadowBlur = 0;

  // Fill area under line
  gx.lineTo(w, h);
  gx.lineTo(0, h);
  gx.closePath();
  gx.globalAlpha = 0.12;
  gx.fillStyle = color;
  gx.fill();
  gx.globalAlpha = 1;
}

// ── Species list ──────────────────────────────────────────────────────────────
function updateSpecies(species) {
  const el  = document.getElementById('sp-list');
  const vals = Object.values(species).map(Number);
  const mx  = Math.max(...vals, 1);
  let html = '';
  let idx = 0;
  for (const [sp, cnt] of Object.entries(species)) {
    const sp_i = parseInt(sp) % 12;
    const col  = SP_COLORS[sp_i];
    const sym  = SP_SYMS[parseInt(sp) % SP_SYMS.length];
    const pct  = (cnt / mx * 100).toFixed(0);
    html += `
      <div class="sp-row">
        <div class="sp-dot" style="background:${col};box-shadow:0 0 5px ${col}80"></div>
        <div class="sp-name">${sym}</div>
        <div class="sp-bar-bg">
          <div class="sp-bar" style="width:${pct}%;background:${col}"></div>
        </div>
        <div class="sp-cnt">${cnt}</div>
      </div>`;
    if (++idx >= 12) break;
  }
  el.innerHTML = html;
}

// ── Events log ────────────────────────────────────────────────────────────────
let lastEvents = [];
function updateEvents(events) {
  if (!events || !events.length) return;
  const el = document.getElementById('events');
  const newOnes = events.filter(e => !lastEvents.includes(e));
  if (!newOnes.length) return;
  lastEvents = [...events];
  el.innerHTML = events.slice().reverse()
    .map(e => `<div class="evt-line">${e}</div>`)
    .join('');
}

// ── DOM stat updates ──────────────────────────────────────────────────────────
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function updateDom(s) {
  setText('h-tick', s.tick.toLocaleString());
  setText('h-pop',  s.pop);
  setText('h-sp',   Object.keys(s.species).length);
  setText('h-gen',  (s.stats && s.stats.max_gen) || 0);
  const spd = document.getElementById('speed-badge');
  if (spd) {
    spd.textContent = s.paused ? '⏸ PAUSED' : `×${s.speed}`;
    spd.style.color = s.paused ? '#ff9900' : 'var(--accent)';
  }

  setText('s-born', s.born.toLocaleString());
  setText('s-died', s.died.toLocaleString());
  setText('s-ext',  s.ext);
  const st = s.stats || {};
  setText('s-mgen', st.max_gen || 0);
  setText('s-aage', st.avg_age ? st.avg_age.toFixed(0) : 0);
  setText('s-anrg', st.avg_energy ? st.avg_energy.toFixed(0) : 0);
  setText('s-mkid', st.max_kids || 0);

  const pb = document.getElementById('btn-pause');
  if (pb) {
    pb.textContent = s.paused ? '▶ Resume' : '⏸ Pause';
    pb.classList.toggle('pressed', s.paused);
  }
}

// ── Control ───────────────────────────────────────────────────────────────────
async function ctrl(cmd) {
  await fetch('/api/control', {
    method:  'POST',
    headers: {'Content-Type': 'application/json'},
    body:    JSON.stringify({cmd}),
  });
}

// ── Main render / fetch loop ──────────────────────────────────────────────────
let state = null;

// Fetch at 20 Hz
async function fetchState() {
  try {
    const r = await fetch('/api/state');
    state = await r.json();
  } catch (e) { /* ignore network blip */ }
}
fetchState();
setInterval(fetchState, 50);

// Render loop at display FPS
let lastRender = 0;
function loop(ts) {
  requestAnimationFrame(loop);
  if (!state) return;

  // Throttle to ~30 FPS for heavy rendering
  if (ts - lastRender < 30) return;
  lastRender = ts;

  renderFood(state.food);
  renderOrgs(state.organisms);
  updateDom(state);
  updateSpecies(state.species);
  updateEvents(state.events);
  drawGraph('pop-graph', state.pop_hist, '#00ffaa');
  drawGraph('div-graph', state.div_hist, '#ffe500');
}
requestAnimationFrame(loop);
</script>
</body>
</html>"""


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import socket

    PORT = 5000
    # Try to find a forwarded URL from common cloud IDE env vars
    public = (
        os.environ.get('CODESPACE_NAME') and
        f"https://{os.environ['CODESPACE_NAME']}-{PORT}.preview.app.github.dev"
    ) or (
        os.environ.get('GITPOD_WORKSPACE_URL') and
        os.environ['GITPOD_WORKSPACE_URL'].replace('https://', f'https://{PORT}-')
    )

    local = f"http://localhost:{PORT}"

    print()
    print("  ┌─────────────────────────────────────────────────────┐")
    print("  │   PRIMORDEA  —  Digital Evolution  (web viewer)     │")
    print("  │                                                     │")
    print(f"  │   Local:   {local:<41}│")
    if public:
        print(f"  │   Public:  {public:<41}│")
    print("  │                                                     │")
    print("  │   Ctrl-C to stop                                    │")
    print("  └─────────────────────────────────────────────────────┘")
    print()

    app.run(host='0.0.0.0', port=PORT, threaded=True, use_reloader=False, debug=False)
