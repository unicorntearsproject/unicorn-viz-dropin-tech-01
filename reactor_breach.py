"""
Reactor Breach — an industrial core meltdown you get to stand inside of.

A single-pass layered fragment effect: a molten reactor core seething at the
center of the frame, plasma vents jetting from randomized ports around it,
rotating hazard beacons sweeping the chamber, and — on every beat — a
**containment wave** that ripples outward, refracting everything it passes,
while a warning strobe slams the room and the camera recoils with a zoom
punch. Hazard striping, rising sparks and heat shimmer sell the plant floor.

Audio-reactive:
  - bass   → core swell + surge glow, zoom punch, room rumble
  - mid    → plasma-vent jet intensity and flicker
  - treble → spark density, heat shimmer
  - beat   → containment wave + warning strobe + camera recoil

Fully randomized at start: per-instance ``iSeed`` re-rolls the vent port
topology and noise fields, a discrete **palette variant** (magma / cherenkov /
toxic) is drawn per activation, the vent count (4–8) and beacon spin direction
are rolled per instance, and ``self.time`` starts at a random phase — no two
breaches ever look alike from frame 0. Tweakables (speed, intensity, zoom,
shake_gain, strobe) ride live from config / MIDI / the control room.
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
// Reactor Breach — molten core + plasma vents + containment waves + strobes.
uniform float iTime;
uniform vec2  iResolution;
uniform float iBass;
uniform float iMid;
uniform float iTreble;
uniform float iWave;      // containment-wave envelope [0,1], 1 = just fired
uniform float iFlash;     // warning-strobe flash envelope [0,1]
uniform float iShake;     // camera recoil envelope [0,1]
uniform float iSurge;     // core surge envelope [0,1]
uniform float iSeed;      // per-instance topology offset
uniform float iSpeed;
uniform float iIntensity;
uniform float iZoomGain;  // bass/beat zoom-punch gain
uniform float iShakeGain;
uniform float iStrobeGain;
uniform float iPalette;   // 0 = magma, 1 = cherenkov, 2 = toxic
uniform float iVents;     // plasma vent count (4..8)
uniform float iSpin;      // beacon spin direction (+1 / -1)
in  vec2 v_pos;
out vec4 fragColor;

float hash11(float n) { return fract(sin(n * 78.233 + iSeed) * 43758.5453); }
float hash21(vec2 p) {
    p = fract(p * vec2(123.34, 456.21) + iSeed);
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}
float vnoise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash21(i), hash21(i + vec2(1, 0)), f.x),
               mix(hash21(i + vec2(0, 1)), hash21(i + vec2(1, 1)), f.x), f.y);
}
float fbm(vec2 p) {
    float v = 0.0, a = 0.55;
    for (int i = 0; i < 3; i++) { v += vnoise(p) * a; p = p * 2.1 + 17.3; a *= 0.5; }
    return v;
}

// Heat ramp per palette variant: cold body -> hot rim -> white-hot core.
vec3 hot(float x) {
    vec3 lo, hi;
    if (iPalette < 0.5)      { lo = vec3(0.55, 0.06, 0.01); hi = vec3(1.0, 0.55, 0.10); }
    else if (iPalette < 1.5) { lo = vec3(0.02, 0.15, 0.60); hi = vec3(0.15, 0.75, 1.0); }
    else                     { lo = vec3(0.05, 0.35, 0.03); hi = vec3(0.65, 0.95, 0.10); }
    vec3 c = mix(lo * 0.25, lo, smoothstep(0.0, 0.45, x));
    c = mix(c, hi, smoothstep(0.4, 0.8, x));
    return mix(c, vec3(1.0, 0.97, 0.9), smoothstep(0.82, 1.0, x));
}

vec3 scene(vec2 uv, float t, float aspect) {
    vec2 p = (uv - 0.5) * vec2(aspect, 1.0);
    // Heat shimmer warps the whole chamber; treble makes the air boil.
    p += (fbm(p * 7.0 + t * 1.6) - 0.5) * (0.006 + iTreble * 0.020);

    // Containment wave: expanding ring that refracts what it passes over.
    float waveR = (1.0 - iWave) * 1.35;
    float r0 = length(p);
    float ring = exp(-pow((r0 - waveR) * 14.0, 2.0));
    p += (p / max(r0, 1e-3)) * ring * iWave * 0.05;

    float r = length(p);
    float ang = atan(p.y, p.x);
    float surge = iBass * 0.8 + iSurge * 0.5;
    vec3 col = hot(0.08) * 0.35 * (1.0 - r);  // ambient chamber glow

    // --- molten core ---
    float coreR = 0.17 * (1.0 + iBass * 0.30 + iSurge * 0.15);
    float mag = fbm(vec2(ang * 2.2 + t * 0.3, r * 7.0 - t * 1.4));
    float body = smoothstep(coreR + 0.02, coreR - 0.06, r);
    col += hot(clamp(0.55 + surge * 0.5 - mag * 0.45 + (1.0 - r / coreR) * 0.35, 0.0, 1.0))
           * body * (0.9 + iIntensity * 0.5);
    col += hot(0.75) * exp(-max(r - coreR, 0.0) * 7.5) * (0.35 + surge * 0.8);

    // --- plasma vents jetting from randomized ports ---
    for (int i = 0; i < 8; i++) {
        if (float(i) >= iVents) break;
        float fi = float(i);
        float va = hash11(fi * 6.7) * 6.2832;
        float da = abs(mod(ang - va + t * 0.05 * iSpin + 3.1416, 6.2832) - 3.1416);
        float jet = smoothstep(0.22, 0.0, da)
                  * smoothstep(coreR, coreR + 0.12, r) * smoothstep(1.0, coreR + 0.2, r)
                  * fbm(vec2(r * 9.0 - t * (2.0 + hash11(fi) * 2.0), fi * 9.0));
        col += hot(0.8) * jet * (0.5 + iMid * 1.6) * iIntensity;
    }

    // --- rotating hazard beacons (two sweeping amber beams) ---
    float sweep = pow(max(cos(ang - t * 1.4 * iSpin), 0.0), 24.0)
                + pow(max(cos(ang - t * 1.4 * iSpin + 3.1416), 0.0), 24.0);
    col += vec3(1.0, 0.55, 0.08) * sweep * smoothstep(coreR, 0.9, r) * (0.10 + iFlash * 0.5);

    // --- containment wave face ---
    col += hot(0.9) * ring * iWave * 1.4;
    col = mix(col, vec3(1.0, 0.2, 0.08), ring * iWave * 0.35 * iStrobeGain);

    // --- rising sparks ---
    vec2 sc = vec2(ang * 3.0, r * 5.0 - t * 2.2);
    float spark = step(0.985 - iTreble * 0.012, hash21(floor(sc * 8.0)));
    col += hot(0.95) * spark * smoothstep(coreR, coreR + 0.4, r) * (0.4 + iTreble);

    // --- hazard striping on the chamber floor/ceiling edges ---
    float band = smoothstep(0.40, 0.47, abs(uv.y - 0.5));
    float stripes = step(0.5, fract((uv.x * aspect + uv.y + t * 0.06) * 9.0));
    col = mix(col, mix(vec3(0.02), vec3(0.85, 0.55, 0.05), stripes) * (0.12 + iFlash * 0.6), band * 0.85);
    return col;
}

void main() {
    vec2 uv = v_pos;
    float t = iTime * (0.8 + iSpeed * 0.5);
    float aspect = iResolution.x / max(iResolution.y, 1.0);

    // Camera recoil + bass rumble.
    float sh = iShake * iShakeGain;
    uv += vec2(sin(t * 73.0), cos(t * 59.0)) * sh * 0.011;
    // Zoom punch into the core on hits.
    uv = 0.5 + (uv - 0.5) / (1.0 + (iBass * 0.10 + iWave * 0.14) * iZoomGain);

    // Chromatic aberration, heavier during waves and recoil.
    vec2 dir = uv - 0.5;
    float ca = 0.0025 + sh * 0.011 + iWave * 0.012;
    vec3 col;
    col.r = scene(uv + dir * ca, t, aspect).r;
    col.g = scene(uv, t, aspect).g;
    col.b = scene(uv - dir * ca, t, aspect).b;

    // Warning strobe: the whole room slams red-white on the beat.
    col += vec3(1.0, 0.32, 0.12) * iFlash * iFlash * 0.6 * iStrobeGain;

    // Bloom on hot cores, vignette, flicker, tonemap.
    col += pow(max(col - 0.6, 0.0), vec3(1.5)) * 1.3;
    col *= 0.96 + 0.04 * hash11(floor(t * 28.0));
    col *= smoothstep(1.35, 0.25, length(uv - 0.5));
    col = col / (1.0 + col * 0.6);
    col = pow(col, vec3(0.88));
    fragColor = vec4(col, 1.0);
}
"""


class ReactorBreach(BaseEffect):
    NAME = "Reactor Breach"
    AUTHOR = "unicorn-viz"
    TAGS = ['tech', 'industrial', 'meltdown', 'plasma', 'intense', 'hard']
    PING_PONG_FRIENDS = [
        # Tech neighbours
        'Threat Matrix',
        'Cyber War',
        'Tron Grid',
        'Hacker Terminal',
        'Hacker Terminal 2.0',
        # Immersive / bass-heavy friends
        'Cathedral of Bass',
        'Wormhole',
        'Tunnel',
        'Black Hole Cathedral',
        # Audio-analysis visualizers
        'Audio Spectrum',
        'Audio Waveforms',
    ]

    def _init(self) -> None:
        self.parameters = {
            "speed": float(self.config.get("speed", 1.0)),
            "intensity": float(self.config.get("intensity", 1.0)),
            "zoom": float(self.config.get("zoom", 1.0)),
            "shake_gain": float(self.config.get("shake_gain", 1.0)),
            "strobe": float(self.config.get("strobe", 1.0)),
            # Startup randomisation: re-roll vent ports + noise topology.
            "seed": float(self.rng.uniform(0.0, 100.0)),
        }
        # Discrete per-activation variety: palette, vent count, spin direction.
        self._palette = float(self.rng.integers(3))
        self._vents = float(self.rng.integers(4, 9))
        self._spin = 1.0 if self.rng.random() < 0.5 else -1.0
        self._bass = 0.0
        self._mid = 0.0
        self._treble = 0.0
        self._wave = 0.0
        self._flash = 0.0
        self._shake = 0.0
        self._surge = 0.0
        self._prog = self._make_program(_VERT, _FRAG)
        self._vao, self._vbo = self._fullscreen_quad(self._prog)

    def update(self, dt: float, audio: AudioData) -> None:
        super().update(dt, audio)
        self._bass = audio.bass_n
        self._mid = audio.mid_n
        self._treble = audio.treble_n
        # Envelopes with decay; a beat re-triggers wave + strobe + recoil.
        self._wave = max(0.0, self._wave - dt * 0.9)
        self._flash = max(0.0, self._flash - dt * 5.0)
        self._shake = max(0.0, self._shake - dt * 3.4)
        self._surge = max(0.0, self._surge - dt * 1.8)
        if audio.beat:
            self._wave = 1.0
            self._flash = 1.0
            self._shake = 1.0
            self._surge = 1.0
        # Heavy low end keeps the floor rumbling between hits.
        self._shake = max(self._shake, self._bass * 0.4)

    def render(self) -> None:
        p = self._prog
        p["iTime"].value = self.time
        p["iResolution"].value = (float(self.width), float(self.height))
        p["iBass"].value = self._bass
        p["iMid"].value = self._mid
        p["iTreble"].value = self._treble
        p["iWave"].value = self._wave
        p["iFlash"].value = self._flash
        p["iShake"].value = self._shake
        p["iSurge"].value = self._surge
        p["iSeed"].value = self.parameters["seed"]
        p["iSpeed"].value = self.parameters["speed"]
        p["iIntensity"].value = self.parameters["intensity"]
        p["iZoomGain"].value = self.parameters["zoom"]
        p["iShakeGain"].value = self.parameters["shake_gain"]
        p["iStrobeGain"].value = self.parameters["strobe"]
        p["iPalette"].value = self._palette
        p["iVents"].value = self._vents
        p["iSpin"].value = self._spin
        self._vao.render(moderngl.TRIANGLE_STRIP)

    def destroy(self) -> None:
        self._vao.release()
        self._vbo.release()
        self._prog.release()
