"""Tron Grid drop-in effect.

Hyper-kinetic Tron / laser-grid effect: a raymarched neon city seen from a
first-person light-cycle view. Features:

  • Infinite scrolling perspective grid with neon line glow
  • Multiple laser beams sweeping the scene (some locked to beat)
  • Volumetric glow on every beam via soft-ray marching
  • Audio-reactive beam thickness, scan frequency, and grid pulse
  • Beat-triggered shockwave ripple through the grid
  • Floating Tron-style data-cube obstacles in the distance
  • Lens-flares and chromatic aberration on bright hits

Config keys (under [effects.TronGrid]):
    speed         float   overall animation speed  (default 1.0)
    num_beams     int     number of sweeping laser beams (default 6)
    grid_scale    float   grid cell size divisor    (default 1.0)
    flare         bool    enable lens flare ("true" / "false", default "true")
"""
from __future__ import annotations

import moderngl

from unicornviz.effects.base import BaseEffect, AudioData

_VERT = """
#version 330
in vec2 in_vert;
out vec2 v_uv;
void main() {
    v_uv = in_vert * 0.5 + 0.5;
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

_FRAG = """
#version 330

uniform float iTime;
uniform vec2  iResolution;
uniform float iBass;
uniform float iMid;
uniform float iTreble;
uniform float iBeat;
uniform float iSpeed;
uniform float iNumBeams;
uniform float iGridScale;
uniform float iZoom;

in  vec2  v_uv;
out vec4  fragColor;

#define PI  3.14159265
#define TAU 6.28318530
uniform int   iSteps;
#define NEAR 0.001
#define FAR  60.0

// ── palette ──────────────────────────────────────────────────────────────────
vec3 neonPalette(float t) {
    // Cycles through cyan → magenta → electric blue
    vec3 a = vec3(0.5, 0.5, 0.5);
    vec3 b = vec3(0.5, 0.5, 0.5);
    vec3 c = vec3(1.0, 1.0, 0.5);
    vec3 d = vec3(0.80, 0.90, 0.30);
    return a + b * cos(TAU * (c * t + d));
}

// ── grid SDF on the xz plane (y = 0) ─────────────────────────────────────────
float sdGrid(vec3 p, float scale) {
    vec2 g = abs(fract(p.xz * scale) - 0.5);
    return min(g.x, g.y) / scale;   // distance to nearest grid line
}

// ── data cube SDF ─────────────────────────────────────────────────────────────
float sdBox(vec3 p, vec3 b) {
    vec3 q = abs(p) - b;
    return length(max(q, 0.0)) + min(max(q.x, max(q.y, q.z)), 0.0);
}

// ── scene SDF (floor + cubes) ─────────────────────────────────────────────────
float sceneDist(vec3 p) {
    float d = p.y;  // floor at y=0
    // Periodic data-cube obstacles
    vec3 id  = round(p / 8.0) * 8.0;
    vec3 lp  = p - id;
    float beat_scale = 1.0 + iBeat * 0.18;
    float box = sdBox(lp - vec3(0.0, 1.0, 0.0), vec3(0.5 * beat_scale, 1.0 * beat_scale, 0.5 * beat_scale));
    // Only spawn cubes in front of the camera (z < -2)
    if (id.z < -2.0) d = min(d, box);
    return d;
}

// ── scene normal ──────────────────────────────────────────────────────────────
vec3 sceneNormal(vec3 p) {
    float e = 0.002;
    return normalize(vec3(
        sceneDist(p + vec3(e, 0, 0)) - sceneDist(p - vec3(e, 0, 0)),
        sceneDist(p + vec3(0, e, 0)) - sceneDist(p - vec3(0, e, 0)),
        sceneDist(p + vec3(0, 0, e)) - sceneDist(p - vec3(0, 0, e))
    ));
}

// ── ray-march ─────────────────────────────────────────────────────────────────
float march(vec3 ro, vec3 rd, out float tHit) {
    float t = NEAR;
    for (int i = 0; i < iSteps; i++) {
        float d = sceneDist(ro + rd * t);
        if (d < 0.001) { tHit = t; return 1.0; }
        t += max(d * 0.6, 0.002);
        if (t > FAR) break;
    }
    tHit = FAR;
    return 0.0;
}

// ── laser beam brightness along a ray ────────────────────────────────────────
float laserBeam(vec3 ro, vec3 rd, vec3 origin, vec3 dir, float thickness) {
    vec3  oc   = ro - origin;
    float b    = dot(oc, dir);
    vec3  perp = oc - b * dir;
    float dist = length(perp);
    return thickness / (dist * dist + thickness * 0.001);
}

// ── main ─────────────────────────────────────────────────────────────────────
void main() {
    vec2 uv = (v_uv * 2.0 - 1.0) * vec2(iResolution.x / iResolution.y, 1.0);
    uv /= max(iZoom, 0.01);

    float t = iTime * iSpeed;

    // Camera: speeding along -Z through the grid corridor
    float shake = iBeat * 0.04;
    vec3 ro = vec3(
        sin(t * 0.22) * 1.6 + shake * sin(t * 19.0),
        1.2 + sin(t * 0.31) * 0.25 + shake * cos(t * 23.0),
        -t * 6.0
    );
    vec3 fwd = normalize(vec3(sin(t * 0.08) * 0.3, -0.12 + shake * 0.6, -1.0));
    vec3 rgt = normalize(cross(fwd, vec3(0.0, 1.0, 0.0)));
    vec3 up  = cross(rgt, fwd);
    float fov = 0.9 + iBass * 0.12;
    vec3 rd  = normalize(fwd + uv.x * rgt * fov + uv.y * up * fov);

    // ── ray-march scene ───────────────────────────────────────────────────────
    float tHit;
    float hit = march(ro, rd, tHit);
    vec3 hp   = ro + rd * tHit;
    vec3 hn   = sceneNormal(hp);

    vec3 col = vec3(0.0);

    if (hit > 0.5) {
        // ── grid lines on floor / cube faces ─────────────────────────────────
        float gs   = iGridScale * (1.0 + iMid * 0.4);
        float gd   = sdGrid(hp, gs);
        float gAmt = smoothstep(0.012, 0.0, gd / gs);
        float gridPulse = 1.0 + iBass * 0.8 + iBeat * 0.5;
        vec3 gridCol = neonPalette(hp.z * 0.005 + t * 0.04) * gridPulse;
        col += gridCol * gAmt * 2.5;

        // ── diffuse ambient for cubes ─────────────────────────────────────────
        if (abs(hn.y) < 0.9) {
            vec3 amb = neonPalette(tHit * 0.012 + t * 0.05) * 0.18;
            col += amb;
        }

        // ── beat shockwave ripple on floor ────────────────────────────────────
        if (hn.y > 0.8) {
            float ring = abs(fract(length(hp.xz - ro.xz) * 0.25 - t * 1.5) - 0.5);
            ring = smoothstep(0.08, 0.0, ring) * iBeat;
            col += ring * vec3(0.3, 0.8, 1.0) * 3.0;
        }

        // Distance fog
        float fog = exp(-tHit * 0.035);
        col *= fog;
    } else {
        // Dark background with distant horizontal scan lines
        float scan = smoothstep(0.01, 0.0, abs(fract(uv.y * 20.0 + t * 0.5) - 0.5));
        col += scan * vec3(0.02, 0.06, 0.12);
    }

    // ── sweeping laser beams ──────────────────────────────────────────────────
    int n = int(clamp(iNumBeams, 2.0, 12.0));
    float beamThick = 0.0004 + iTreble * 0.0008 + iBass * 0.001;
    for (int i = 0; i < 12; i++) {
        if (i >= n) break;
        float fi  = float(i);
        float off = fi * TAU / float(n);
        float spd = 0.5 + fi * 0.07;

        // Beam origin high above, rotating
        vec3 bOri = vec3(sin(t * spd + off) * 4.0, 8.0, ro.z - 3.0);
        vec3 bDir = normalize(vec3(
            cos(t * spd * 0.7 + off + 1.0),
            -0.7 + sin(t * 0.3 + off) * 0.2,
            sin(t * spd * 0.4 + off + 2.3)
        ));

        float bGlow = laserBeam(ro, rd, bOri, bDir, beamThick);
        vec3  bCol  = neonPalette(fi / float(n) + t * 0.06);
        col += bCol * bGlow * (0.6 + iBass * 0.5 + iBeat * 0.8);
    }

    // ── lens flare from brightest beam ────────────────────────────────────────
    {
        vec3 flareOri = vec3(0.0, 8.0, ro.z - 3.0);
        vec2 flareUV  = v_uv - 0.5;
        float flareDist = length(flareUV);
        float flare = 0.003 / (flareDist * flareDist + 0.0001);
        flare *= 1.0 + iTreble * 2.0 + iBeat;
        col += vec3(0.6, 0.85, 1.0) * flare * 0.15;
    }

    // ── chromatic aberration fringe ───────────────────────────────────────────
    {
        float abr   = 0.003 + iBass * 0.005;
        vec2  oUV   = v_uv - 0.5;
        float rShift = length(oUV) * abr;
        col.r *= 1.0 + rShift;
        col.b *= max(0.0, 1.0 - rShift);
    }

    // ── vignette ─────────────────────────────────────────────────────────────
    vec2  cv  = v_uv - 0.5;
    float vig = 1.0 - 0.55 * dot(cv, cv) * 4.0;
    col *= vig;

    // ── filmic tone-map ───────────────────────────────────────────────────────
    col = col / (col + 0.6);
    col = pow(max(col, 0.0), vec3(0.88));

    fragColor = vec4(col, 1.0);
}
"""


class TronGrid(BaseEffect):
    """Hyper-kinetic Tron / laser-grid fly-through effect.

    A raymarched infinite neon grid corridor at night, with sweeping coloured
    laser beams, volumetric glow, beat-triggered shockwaves, data-cube
    obstacles, lens flares, and chromatic aberration.
    """

    NAME = 'Tron Grid'
    AUTHOR = 'unicorn-viz drop-in'
    TAGS = ['tech', 'tron', 'laser', 'grid', 'raymarching', 'neon', 'sci-fi', 'intense']
    PING_PONG_FRIENDS = [
        'Hacker Terminal',
        'Cyber War',
        'Escher',
        'Hexy Stars',
        'Metaballs',
        'Wormhole',
        'Tunnel',
        'Kaleidoscope',
        'Unicorn Tears',
    ]

    def _init(self) -> None:
        self.parameters = {
            'speed':      float(self.config.get('speed',      1.0)),
            'num_beams':  float(self.config.get('num_beams',  6)),
            'grid_scale': float(self.config.get('grid_scale', 1.0)),
            'zoom': float(self.config.get('zoom', 1.0)),
            # Ray-march budget: the config editor's Effects tab pins it live.
            'march_steps': float(self.config.get('march_steps', 64)),
        }
        self._flare = str(self.config.get('flare', 'true')).lower() != 'false'

        self._prog = self._make_program(_VERT, _FRAG)
        self._vao, self._vbo = self._fullscreen_quad(self._prog)

        self._bass   = 0.0
        self._mid    = 0.0
        self._treble = 0.0
        self._beat   = 0.0

    def update(self, dt: float, audio: AudioData) -> None:
        super().update(dt, audio)
        self._bass   = audio.bass_n
        self._mid    = audio.mid_n
        self._treble = audio.treble_n
        self._beat   = max(0.0, self._beat - dt * 5.0)
        if audio.beat:
            self._beat = 1.0

    def _set(self, name: str, value) -> None:
        try:
            self._prog[name].value = value
        except KeyError:
            pass

    def render(self) -> None:
        self._set('iTime',       self.time)
        self._set('iResolution', (float(self.width), float(self.height)))
        self._set('iBass',       self._bass)
        self._set('iMid',        self._mid)
        self._set('iTreble',     self._treble)
        self._set('iBeat',       self._beat)
        self._set('iSpeed',      max(0.05, self.parameters['speed']))
        self._set('iNumBeams',   max(2.0, self.parameters['num_beams']))
        self._set('iGridScale',  max(0.2, self.parameters['grid_scale']))
        self._set('iZoom',       max(0.1, self.parameters['zoom']))
        self._set('iSteps',      int(max(8, min(256, self.parameters['march_steps']))))
        self._vao.render(moderngl.TRIANGLE_STRIP)

    def destroy(self) -> None:
        self._vao.release()
        self._vbo.release()
        self._prog.release()
