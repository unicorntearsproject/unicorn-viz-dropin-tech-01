"""
Hacker Terminal 2.0 — real CP437-style scrolling text streams with audio-reactive glitch.

Unlike the 1.0 version (which simulates a terminal aesthetic via shader noise),
this effect renders actual scrolling log lines as rasterised CP437 glyph columns
using a glyph-atlas texture sampled in GLSL.  Each column scrolls at an
independent rate driven by audio; beats trigger burst lines and glitch
displacement.

Audio reactivity:
  - bass  → column scroll speed + overall brightness surge
  - treble → character flicker density per column
  - beat  → glitch displacement row + burst of 3-5 new log lines
  - mid   → hue shift of the terminal phosphor colour
"""
from __future__ import annotations

__version__ = '0.11.0'

import math
import random

import moderngl
import numpy as np

from unicornviz.effects.base import BaseEffect, AudioData

# ---------------------------------------------------------------------------
# Glyph atlas constants (font8x16 CP437 atlas: 16 cols × 16 rows of 8×16px glyphs)
# ---------------------------------------------------------------------------
_GLYPH_COLS  = 16
_GLYPH_ROWS  = 16
_GLYPH_W     = 8
_GLYPH_H     = 16

# ---------------------------------------------------------------------------
# How many text columns / rows the terminal draws
# ---------------------------------------------------------------------------
_TERM_COLS = 80
_TERM_ROWS = 30

# ---------------------------------------------------------------------------
# Vertex shader — fullscreen quad, passes UV through.
# ---------------------------------------------------------------------------
_VERT = """
#version 330
in vec2 in_vert;
out vec2 v_uv;
void main() {
    v_uv = in_vert * 0.5 + 0.5;
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

# ---------------------------------------------------------------------------
# Fragment shader — samples the glyph atlas per character cell.
# The CPU side uploads a flat int array (iGlyphs[ROWS*COLS]) where each
# entry is the CP437 codepoint for that cell.  The shader maps screen UV
# → cell → glyph UV → atlas sample.
#
# Uniforms
#   iTime          — global time
#   iBass          — bass energy [0,1]
#   iMid           — mid energy  [0,1]
#   iTreble        — treble energy [0,1]
#   iBeat          — beat decay [0,1]
#   iSpeed         — base scroll speed multiplier
#   iZoom          — viewport zoom
#   iPhosphor      — phosphor hue (0=green, 0.5=amber, 1=blue)
#   iGlitchAmt     — glitch displacement magnitude
#   iFont          — CP437 8×16 atlas sampler
#   iScrollY[C]    — per-column fractional scroll offset [0,1)
#   iFlicker[C]    — per-column brightness flicker [0,1]
#   iGlyphs[R*C]   — per-cell glyph index (int)
# ---------------------------------------------------------------------------
_FRAG = """
#version 330
#define COLS 80
#define ROWS 30

uniform float iTime;
uniform float iBass;
uniform float iMid;
uniform float iTreble;
uniform float iBeat;
uniform float iSpeed;
uniform float iZoom;
uniform float iPhosphor;
uniform float iGlitchAmt;
uniform sampler2D iFont;
uniform float iScrollY[COLS];
uniform float iFlicker[COLS];
uniform int   iGlyphs[COLS * ROWS];

in  vec2 v_uv;
out vec4 fragColor;

float hash(vec2 p) {
    p = fract(p * vec2(127.1, 311.7));
    p += dot(p, p + 19.19);
    return fract(p.x * p.y);
}

// CRT scanline dim
float scanline(float y, float t) {
    return 0.72 + 0.28 * sin(y * 3.14159 * 2.0 * float(ROWS) * 16.0 + t * 0.4);
}

// Phosphor palette: green / amber / cold-blue
vec3 phosphor(float hue, float brightness) {
    vec3 green = vec3(0.08, 1.0, 0.35);
    vec3 amber = vec3(1.0,  0.72, 0.06);
    vec3 blue  = vec3(0.22, 0.68, 1.0);
    vec3 col;
    if (hue < 0.5) {
        col = mix(green, amber, hue * 2.0);
    } else {
        col = mix(amber, blue, (hue - 0.5) * 2.0);
    }
    return col * brightness;
}

void main() {
    vec2 uv = v_uv;
    uv = (uv - 0.5) / max(iZoom, 0.1) + 0.5;

    // Beat-driven row glitch: shift a band of rows horizontally.
    // mod() before the hash: floor(iTime*8) * 127.1 exceeds 2^23 past
    // iTime ~8k (start phase reaches 10k), freezing the glitch row at a
    // fixed position for the whole session.
    float glitch_row = hash(vec2(floor(mod(iTime, 512.0) * 8.0), 0.0));
    float row_band = abs(uv.y - glitch_row);
    float gshift = iGlitchAmt * iBeat * smoothstep(0.08, 0.0, row_band);
    uv.x = fract(uv.x + gshift * 0.045);

    // Map uv to character cell
    float col_f = uv.x * float(COLS);
    float row_f = uv.y * float(ROWS);
    int   col_i = int(clamp(col_f, 0.0, float(COLS) - 1.0));
    int   row_i = int(clamp(row_f, 0.0, float(ROWS) - 1.0));

    // Sub-cell UV with per-column scroll applied
    vec2 cell_uv = vec2(fract(col_f), fract(row_f + iScrollY[col_i]));

    // Look up glyph index for this cell
    int glyph_idx = iGlyphs[row_i * COLS + col_i];

    // Map glyph index to atlas UV (16×16 glyph grid)
    float atlas_col = float(glyph_idx & 15);
    float atlas_row = float(glyph_idx >> 4);
    vec2 atlas_uv = (vec2(atlas_col, atlas_row) + cell_uv)
                    / vec2(16.0, 16.0);
    // Flip V: atlas row 0 is top in image, OpenGL UV 0 is bottom
    atlas_uv.y = 1.0 - atlas_uv.y;

    float glyph_sample = texture(iFont, atlas_uv).r;

    // Brightness: scanline × per-column flicker × treble sparkle
    float flicker = iFlicker[col_i];
    // mod() for the same 2^23 reason as glitch_row above (×311.7 here).
    float sparkle = 1.0 + iTreble * 0.35 * hash(vec2(col_f, mod(iTime, 1024.0) * 4.0));
    float brightness = glyph_sample * scanline(uv.y, iTime) * flicker * sparkle;

    // CRT bloom: soft glow around bright pixels
    float bloom = glyph_sample * (0.04 + iBass * 0.06);

    // Phosphor hue shifts slowly with mid
    float hue = fract(iPhosphor + iMid * 0.08);
    vec3 col = phosphor(hue, brightness + bloom);

    // Slight vignette
    float vig = 1.0 - 0.45 * pow(length(uv - 0.5) * 1.6, 2.2);
    col *= vig;

    // Beat flash
    col += phosphor(hue, 1.0) * iBeat * 0.07;

    fragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}
"""

# ---------------------------------------------------------------------------
# Log-line content pools
# ---------------------------------------------------------------------------
_PREFIXES = [
    '[INFO]', '[WARN]', '[ERROR]', '[DEBUG]', '[TRACE]',
    '>>>', '$', '#', 'root@host:~#', '0x{:04X}  '.format,
]
_MESSAGES = [
    lambda rng: 'Scanning network interfaces...',
    lambda rng: f'AES-256 encryption key: {rng.getrandbits(128):032X}',
    lambda rng: f'Firewall rule bypass: port {rng.randint(1024, 65535)}',
    lambda rng: (
        f'TCP SYN flood detected from '
        f'{rng.randint(1, 255)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}'
    ),
    lambda rng: f'Data exfil {rng.randint(1, 99)}% complete',
    lambda rng: 'Signal carrier jammed',
    lambda rng: 'Kernel module injected',
    lambda rng: f'System reboot deferred: {rng.randint(5, 240)}s',
    lambda rng: (
        f'SSH session opened: root@'
        f'{rng.randint(1, 255)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}'
    ),
    lambda rng: f'Protocol mismatch on fd {rng.randint(3, 255)}',
    lambda rng: f'Heap spray: base=0x{rng.getrandbits(32):08X}',
    lambda rng: f'Buffer overflow: EIP=0x{rng.getrandbits(32):08X}',
    lambda rng: f'Privilege escalation: uid {rng.randint(1000, 65534)} -> 0',
    lambda rng: f'/dev/mem mapped: {rng.randint(4, 8192)} pages',
    lambda rng: f'Packet capture: {rng.randint(64, 50000)} frames',
]


def _gen_line(rng: random.Random) -> str:
    """Generate one pseudo-realistic terminal log line."""
    prefix = rng.choice(_PREFIXES)
    if callable(prefix):
        prefix = prefix(rng.randint(0, 0xFFFF))
    msg = rng.choice(_MESSAGES)(rng)
    return f'{prefix} {msg}'


def _text_to_glyphs(text: str, width: int) -> list[int]:
    """Convert a string to a list of CP437 codepoints, padded/truncated to width."""
    out = []
    for ch in text[:width]:
        cp = ord(ch)
        # Map basic ASCII; non-printable → space
        out.append(cp if 0x20 <= cp <= 0x7E else 0x20)
    while len(out) < width:
        out.append(0x20)
    return out


class HackerTerminal2(BaseEffect):
    """Hacker Terminal 2.0 — real CP437 scrolling text with audio-reactive glitch."""

    NAME   = 'Hacker Terminal 2.0'
    AUTHOR = 'unicorn-viz'
    TAGS = ['tech', 'cyberpunk', 'glitch', 'text', 'energetic', 'intense']
    PING_PONG_FRIENDS = ['Tron Grid', 'Cyber War', 'Hacker Terminal']

    def _init(self) -> None:
        self.candy_frame_disallow = bool(self.config.get('candy_frame_disallow', True))
        self.scale_when_framed    = bool(self.config.get('scale_when_framed', False))
        self.parameters = {
            'speed':       float(self.config.get('speed', 1.0)),
            'zoom':        float(self.config.get('zoom', 1.0)),
            'phosphor':    float(self.config.get('phosphor', 0.0)),  # 0=green, 0.5=amber, 1=blue
            'glitch':      float(self.config.get('glitch', 0.8)),
        }

        self._prog = self._make_program(_VERT, _FRAG)
        self._vao, self._vbo = self._fullscreen_quad(self._prog)

        # Load CP437 font atlas (assets/fonts/font8x16.bin or fallback white texture)
        self._font_tex = self._load_font()

        # Per-column scroll state
        self._scroll_y  = np.zeros(_TERM_COLS, dtype=np.float32)
        self._scroll_spd = np.array(
            [float(self.rng.uniform(0.4, 1.6)) for _ in range(_TERM_COLS)],
            dtype=np.float32,
        )
        self._flicker   = np.ones(_TERM_COLS, dtype=np.float32)

        # Glyph buffer: ROWS × COLS of codepoints
        self._glyphs = np.full((_TERM_ROWS, _TERM_COLS), 0x20, dtype=np.int32)
        self._glyphs_dirty = True

        # Text line buffer
        self._rng_py = random.Random(int(self.rng.integers(0, 2**31)))
        self._lines: list[str] = [
            _gen_line(self._rng_py) for _ in range(_TERM_ROWS)
        ]
        self._flush_glyphs()

        # Startup variance
        self._phosphor = float(self.rng.uniform(0.0, 1.0)) \
            if self.config.get('phosphor') is None else self.parameters['phosphor']
        self._line_timer = 0.0
        self._beat = 0.0
        self._bass = 0.0
        self._mid  = 0.0
        self._treble = 0.0
        self._glitch_amt = 0.0

    # ------------------------------------------------------------------

    def _load_font(self) -> moderngl.Texture:
        """Load font8x16 atlas from assets or fall back to a white 128×128 texture."""
        from pathlib import Path

        candidates = [
            Path('assets/fonts/font8x16.bin'),
            Path('drop-ins/hacker-terminal-01/assets/font8x16.bin'),
        ]
        atlas_w = _GLYPH_COLS * _GLYPH_W   # 128
        atlas_h = _GLYPH_ROWS * _GLYPH_H   # 256

        for path in candidates:
            if path.exists():
                raw = path.read_bytes()
                if len(raw) >= atlas_w * atlas_h:
                    tex = self.ctx.texture((atlas_w, atlas_h), 1, data=raw[:atlas_w * atlas_h])
                    tex.filter = moderngl.NEAREST, moderngl.NEAREST
                    return tex

        # Fallback: solid white — all cells will show bright rectangles
        data = bytes([0xFF] * (atlas_w * atlas_h))
        tex = self.ctx.texture((atlas_w, atlas_h), 1, data=data)
        tex.filter = moderngl.NEAREST, moderngl.NEAREST
        return tex

    def _flush_glyphs(self) -> None:
        """Copy self._lines into the self._glyphs integer array."""
        for r, line in enumerate(self._lines[-_TERM_ROWS:]):
            row = _text_to_glyphs(line, _TERM_COLS)
            self._glyphs[r] = row
        self._glyphs_dirty = True

    # ------------------------------------------------------------------

    def update(self, dt: float, audio: AudioData) -> None:
        super().update(dt, audio)
        self._bass   = audio.bass_n
        self._mid    = audio.mid_n
        self._treble = audio.treble_n

        if audio.beat > 0.35:
            self._beat = 1.0
            # Beat → burst 3-5 new lines
            n = self._rng_py.randint(3, 5)
            for _ in range(n):
                self._lines.append(_gen_line(self._rng_py))
            if len(self._lines) > _TERM_ROWS * 3:
                self._lines = self._lines[-_TERM_ROWS * 2:]
            self._flush_glyphs()

        self._beat = max(0.0, self._beat - dt * 3.5)

        # Slow new-line drip when no beat
        speed = max(0.05, float(self.parameters['speed']))
        self._line_timer += dt
        interval = 0.38 / max(0.2, speed * (0.8 + self._mid * 0.6))
        if self._line_timer >= interval:
            self._line_timer = 0.0
            self._lines.append(_gen_line(self._rng_py))
            if len(self._lines) > _TERM_ROWS * 3:
                self._lines = self._lines[-_TERM_ROWS * 2:]
            self._flush_glyphs()

        # Scroll each column at its own rate
        scroll_scale = speed * (0.55 + self._bass * 0.90)
        self._scroll_y = (self._scroll_y + self._scroll_spd * scroll_scale * dt) % 1.0

        # Per-column flicker driven by treble
        for c in range(_TERM_COLS):
            base = 0.72 + 0.28 * float(self.rng.uniform(0.0, 1.0))
            self._flicker[c] = float(np.clip(base + self._treble * 0.22, 0.45, 1.0))

        self._glitch_amt = max(0.0, self._glitch_amt - dt * 4.0)
        if audio.beat > 0.35:
            self._glitch_amt = min(1.0, self._glitch_amt + float(self.parameters['glitch']))

        # Slow phosphor hue drift
        self._phosphor = math.fmod(
            self._phosphor + dt * 0.012 * speed + self._mid * dt * 0.04, 1.0
        )

    def render(self) -> None:
        def _set(name: str, value) -> None:
            try:
                self._prog[name].value = value
            except KeyError:
                # Some drivers optimize unused uniforms out of the program.
                pass

        self._font_tex.use(location=0)
        _set('iFont', 0)
        _set('iTime', self.time)
        _set('iBass', self._bass)
        _set('iMid', self._mid)
        _set('iTreble', self._treble)
        _set('iBeat', self._beat)
        _set('iSpeed', float(self.parameters['speed']))
        _set('iZoom', float(self.parameters['zoom']))
        _set('iPhosphor', self._phosphor)
        _set('iGlitchAmt', self._glitch_amt)
        _set('iScrollY', tuple(float(v) for v in self._scroll_y))
        _set('iFlicker', tuple(float(v) for v in self._flicker))
        # Glyph content only changes on beat/drip (_flush_glyphs); the
        # unconditional upload boxed ~2,500 Python objects per frame for a
        # mostly-static 2,400-int array.
        if self._glyphs_dirty:
            _set('iGlyphs', tuple(int(v) for v in self._glyphs.flatten()))
            self._glyphs_dirty = False
        self._vao.render(moderngl.TRIANGLE_STRIP)

    def destroy(self) -> None:
        self._vao.release()
        self._vbo.release()
        self._prog.release()
        self._font_tex.release()
