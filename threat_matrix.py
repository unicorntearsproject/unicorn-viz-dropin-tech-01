"""
Threat Matrix — a war-room global threat map for the terminal faithful.

A single-pass, heavily layered fragment effect built to read like a live
intrusion-detection wall: a phosphor-green heat grid of "sectors" that flare with
the low end, animated trace-routes with travelling packets stitching nodes
across the map, a slow radar scan line, cascading matrix rain in the deep
background, and — on every beat — a red **breach wave** that ripples out from the
core, slams the room with a shake + zoom of chromatic aberration, and stains the
sectors it passes crimson.  CRT scanlines, phosphor bloom, edge vignette and a
mains-hum flicker sell the old-glass look.

Audio-reactive:
  - bass   → sector heat surge, breach intensity, room shake
  - mid    → trace-packet brightness, node flares
  - treble → matrix-rain density, scan sparkle
  - beat   → breach wave + shake recoil + chromatic punch

Per-instance ``iSeed`` re-rolls the sector heat map and trace-route topology, and
``self.time`` starts at a random phase, so no two runs look alike from frame 0.
Tweakables (speed, intensity, shake_gain, rain, breach) ride live from config /
MIDI / the control room.
"""
from __future__ import annotations

import moderngl

from unicornviz.effects.base import BaseEffect, AudioData

_VERT = """
#version 330
in vec2 in_vert;
out vec2 v_pos;
void main() {
    v_pos = in_vert * 0.5 + 0.5;
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

_FRAG = """
#version 330
// Threat Matrix — layered IDS war-room map with beat-driven breach waves.
uniform float iTime;
uniform vec2  iResolution;
uniform float iBass;
uniform float iMid;
uniform float iTreble;
uniform float iBreach;     // beat breach-wave envelope [0,1]
uniform float iShake;      // beat/bass shake envelope [0,1]
uniform float iSeed;       // per-instance topology offset
uniform float iSpeed;
uniform float iIntensity;
uniform float iShakeGain;
uniform float iRain;       // matrix-rain gain
uniform float iBreachGain; // breach-wave gain
in  vec2 v_pos;
out vec4 fragColor;

float hash11(float n) { return fract(sin(n * 78.233 + iSeed) * 43758.5453); }
float hash21(vec2 p) {
    p = fract(p * vec2(123.34, 456.21) + iSeed);
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

float sdSeg(vec2 p, vec2 a, vec2 b) {
    vec2 pa = p - a, ba = b - a;
    float h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
    return length(pa - ba * h);
}

// 4x6 dot-matrix pseudo-glyph inside a cell coordinate.
float glyph(vec2 c, float seed) {
    vec2 g = floor(c * vec2(4.0, 6.0));
    return step(0.55, hash21(g + seed * 13.7));
}

// green -> amber -> red threat ramp
vec3 heatRamp(float h) {
    vec3 c = mix(vec3(0.10, 0.95, 0.35), vec3(1.0, 0.72, 0.12), smoothstep(0.35, 0.7, h));
    return mix(c, vec3(1.0, 0.16, 0.12), smoothstep(0.7, 1.0, h));
}

vec3 scene(vec2 uv, float t, float aspect) {
    vec3 col = vec3(0.008, 0.028, 0.018);
    vec2 ar = vec2(uv.x * aspect, uv.y);

    // --- matrix rain (deep background) ---
    vec2 rc = floor(vec2(ar.x * 40.0, ar.y * 24.0));
    float stream = fract(uv.y * 24.0 + t * (0.6 + hash11(rc.x) * 1.8) + hash11(rc.x) * 10.0);
    float head = smoothstep(0.0, 0.08, stream) * smoothstep(0.6, 0.08, stream);
    float gl = glyph(fract(vec2(ar.x * 40.0, ar.y * 24.0)), rc.x + floor(t * 8.0 + rc.y));
    col += vec3(0.05, 0.55, 0.18) * gl * head * (0.2 + iTreble * 0.7) * iRain;

    // --- threat heat grid ---
    float cells = 14.0;
    vec2 gp = ar * cells;
    vec2 cid = floor(gp);
    vec2 cf = fract(gp);
    float base = hash21(cid);
    float heat = 0.5 + 0.5 * sin(t * 0.6 + base * 20.0);
    heat = clamp(heat * 0.55 + iBass * 0.85 * step(0.68, base) + iMid * 0.3, 0.0, 1.0);
    float border = min(min(cf.x, cf.y), min(1.0 - cf.x, 1.0 - cf.y));
    float edge = smoothstep(0.04, 0.0, border);
    float coreGlow = smoothstep(0.5, 0.0, length(cf - 0.5)) * heat;
    col += heatRamp(heat) * (edge * 0.22 + coreGlow * 0.72) * (0.6 + iIntensity * 0.6);

    // --- trace routes + travelling packets ---
    float traces = 0.0;
    vec3 packets = vec3(0.0);
    vec2 p = ar;
    for (int i = 0; i < 5; i++) {
        float fi = float(i);
        vec2 a = vec2(hash11(fi * 3.1) * aspect, hash11(fi * 7.7));
        vec2 b = vec2(hash11(fi * 5.3 + 2.0) * aspect, hash11(fi * 9.1 + 1.0));
        traces += smoothstep(0.006, 0.0, sdSeg(p, a, b)) * 0.25;
        float tp = fract(t * (0.25 + 0.15 * fi) + fi * 0.2);
        packets += vec3(0.2, 1.0, 0.6) * smoothstep(0.02, 0.0, length(p - mix(a, b, tp))) * (0.7 + iMid);
    }
    col += vec3(0.10, 0.75, 0.35) * traces * 0.5 + packets;

    // --- radar scan sweep ---
    col += vec3(0.2, 1.0, 0.5) * smoothstep(0.06, 0.0, abs(uv.y - fract(t * 0.12))) * 0.16;

    // --- breach wave (beat) ---
    float r = length((uv - 0.5) * vec2(aspect, 1.0));
    float ring = smoothstep(0.055, 0.0, abs(r - iBreach * 0.95));
    col = mix(col, vec3(1.0, 0.15, 0.12), ring * iBreach * 0.85 * iBreachGain);
    col += vec3(1.0, 0.22, 0.1) * ring * iBreach * iBreachGain;
    col += vec3(1.0, 0.25, 0.15) * exp(-r * 3.0) * iBreach * 0.55;
    return col;
}

void main() {
    vec2 uv = v_pos;
    float t = iTime * (0.8 + iSpeed * 0.5);
    float aspect = iResolution.x / max(iResolution.y, 1.0);

    // Room shake + breach recoil.
    float sh = iShake * iShakeGain;
    uv += vec2(sin(t * 70.0), cos(t * 61.0)) * sh * 0.010;

    // Radial chromatic aberration — stronger on hits and toward the edges.
    vec2 dir = uv - 0.5;
    float ca = 0.002 + sh * 0.012 + iBreach * 0.012;
    vec3 col;
    col.r = scene(uv + dir * ca, t, aspect).r;
    col.g = scene(uv, t, aspect).g;
    col.b = scene(uv - dir * ca, t, aspect).b;

    // Cheap phosphor bloom on bright cores.
    col += pow(max(col - 0.55, 0.0), vec3(1.6)) * 1.4;

    // CRT scanlines + mains-hum flicker.
    col *= 0.9 + 0.1 * sin(uv.y * iResolution.y * 1.6);
    col *= 0.95 + 0.05 * hash11(floor(t * 30.0));

    // Vignette + tonemap + phosphor grade.
    col *= smoothstep(1.25, 0.2, length(uv - 0.5));
    col = col / (1.0 + col * 0.7);
    col = pow(col, vec3(0.85));
    fragColor = vec4(col, 1.0);
}
"""


class ThreatMatrix(BaseEffect):
    NAME = "Threat Matrix"
    AUTHOR = "unicorn-viz"
    TAGS = ["tech", "cyberpunk", "hacker", "network", "matrix"]
    PING_PONG_FRIENDS = [
        # Tech neighbours
        'Cyber War',
        'Tron Grid',
        'Hacker Terminal',
        'Hacker Terminal 2.0',
        # Immersive / bass-heavy friends
        'Cathedral of Bass',
        'Wormhole',
        'Tunnel',
        # Audio-analysis visualizers
        'Audio Spectrum',
        'Audio Spectrogram',
        'Audio Tracks',
        'Audio Waveforms',
        'Audio Centroid',
        'Audio Sine',
    ]

    def _init(self) -> None:
        self.parameters = {
            "speed": float(self.config.get("speed", 1.0)),
            "intensity": float(self.config.get("intensity", 1.0)),
            "shake_gain": float(self.config.get("shake_gain", 1.0)),
            "rain": float(self.config.get("rain", 1.0)),
            "breach": float(self.config.get("breach", 1.0)),
            # Startup randomisation: re-roll the sector map + trace topology.
            "seed": float(self.rng.uniform(0.0, 100.0)),
        }
        self._bass = 0.0
        self._mid = 0.0
        self._treble = 0.0
        self._breach = 0.0
        self._shake = 0.0
        self._prog = self._make_program(_VERT, _FRAG)
        self._vao, self._vbo = self._fullscreen_quad(self._prog)

    def update(self, dt: float, audio: AudioData) -> None:
        super().update(dt, audio)
        self._bass = audio.bass_n
        self._mid = audio.mid_n
        self._treble = audio.treble_n
        # Breach + shake envelopes with decay; a beat re-triggers both.
        self._breach = max(0.0, self._breach - dt * 1.5)
        self._shake = max(0.0, self._shake - dt * 3.6)
        if audio.beat:
            self._breach = 1.0
            self._shake = 1.0
        # Heavy low end keeps the room trembling between hits.
        self._shake = max(self._shake, self._bass * 0.35)

    def render(self) -> None:
        p = self._prog
        p["iTime"].value = self.time
        p["iResolution"].value = (float(self.width), float(self.height))
        p["iBass"].value = self._bass
        p["iMid"].value = self._mid
        p["iTreble"].value = self._treble
        p["iBreach"].value = self._breach
        p["iShake"].value = self._shake
        p["iSeed"].value = self.parameters["seed"]
        p["iSpeed"].value = self.parameters["speed"]
        p["iIntensity"].value = self.parameters["intensity"]
        p["iShakeGain"].value = self.parameters["shake_gain"]
        p["iRain"].value = self.parameters["rain"]
        p["iBreachGain"].value = self.parameters["breach"]
        self._vao.render(moderngl.TRIANGLE_STRIP)

    def destroy(self) -> None:
        self._vao.release()
        self._vbo.release()
        self._prog.release()
