"""
Hacker Terminal — Animated shell/log streams with audio-reactive glitch transitions.
Simulates a hacker/sysadmin terminal with real-time log output, signal traces,
and beat-driven glitch effects.
"""
from __future__ import annotations

import random
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
uniform float iBass;
uniform float iMid;
uniform float iBeat;
uniform float iTreble;
uniform float iZoom;
uniform float iSpeed;
uniform float iReactivity;
uniform float iGlitchSensitivity;
uniform float iStyleA;
uniform float iStyleB;
uniform sampler2D iFont;
in vec2 v_uv;
out vec4 fragColor;

// Pseudo-random based on position
float hash(vec2 p) {
    return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

// CRT scanline effect
float scanlines(vec2 uv, float time) {
    return 0.5 + 0.5 * sin((uv.y + time * 0.5) * 200.0);
}

void main() {
    vec2 uv = v_uv;
    uv = (uv - 0.5) / max(iZoom, 0.01) + 0.5;
    float t = iTime * max(iSpeed, 0.05);
    float react = max(iReactivity, 0.05);
    float glitch_gain = max(iGlitchSensitivity, 0.0);
    
    // Glitch effect triggered by beat
    float beat_glitch = iBeat * (0.18 + iTreble * react * 0.45);
    float bass_glitch = iBass * react * 0.12;
    float glitch_intensity = clamp((beat_glitch + bass_glitch) * (0.55 + iStyleA * 0.22) * glitch_gain, 0.0, 1.15);
    uv.x += glitch_intensity * sin(uv.y * (90.0 + iStyleA * 40.0) + t * 16.0) * 0.012;
    uv.y += glitch_intensity * cos(uv.x * (135.0 + iStyleB * 60.0) + t * 11.0) * 0.0065;
    
    // CRT scanlines
    float scan = scanlines(uv, t) * (0.80 + iTreble * react * 0.35);
    
    // Terminal green color with glow (darker baseline)
    vec3 base_green = mix(vec3(0.0, 0.68, 0.24), vec3(0.03, 0.84, 0.44), iStyleB);
    vec3 col = base_green * (0.50 + iMid * react * 0.40);
    
    // Text region simulation
    float text_region = step(0.1, uv.y) * step(uv.y, 0.9);
    col *= text_region * scan;
    
    // Top-bar status
    float top_bar = smoothstep(0.05, 0.01, abs(uv.y - 0.1)) * (0.40 + iBass * react * 0.35);
    col += vec3(0.14, 0.58, 0.78) * top_bar;
    
    // Vertical signal trace
    float trace = abs(sin(uv.x * (48.0 + iStyleA * 18.0) + t * (4.0 + iMid * react * 3.0) + sin(uv.y * 20.0)));
    float signal = smoothstep(0.3, 0.0, trace) * smoothstep(0.3, 0.0, abs(uv.y - 0.5));
    col += vec3(0.0, 0.82, 0.46) * signal * (0.45 + iMid * react * 0.70);
    
    // Noise/glitch overlay
    float noise = hash(uv + t * (0.12 + iStyleB * 0.08));
    col += vec3(noise) * glitch_intensity * (0.10 + iStyleA * 0.10);
    
    // Bloom glow
    float glow = exp(-distance(uv, vec2(0.5, 0.5)) * 2.0);
    col += vec3(0.0, 0.34, 0.14) * glow * (0.07 + iTreble * react * 0.20);

    // Global tone map: slightly darker with stronger mid/high contrast.
    col = max(col - vec3(0.025), vec3(0.0));
    col = pow(clamp(col, 0.0, 1.0), vec3(1.22));
    col = clamp((col - 0.5) * 1.20 + 0.5, 0.0, 1.0);
    
    fragColor = vec4(col, 1.0);
}
"""

class HackerTerminal(BaseEffect):
    NAME = "Hacker Terminal"
    AUTHOR = "Autopilot"
    TAGS = ['tech', 'cyberpunk', 'glitch', 'energetic', 'intense']
    PING_PONG_FRIENDS = ['Tron Grid', 'Cyber War']

    def _init(self) -> None:
        self.candy_frame_disallow = bool(self.config.get('candy_frame_disallow', True))
        self.scale_when_framed = bool(self.config.get('scale_when_framed', False))
        self.parameters = {
            'speed': float(self.config.get('speed', 1.0)),
            'reactivity': float(self.config.get('reactivity', 1.35)),
            'glitch_sensitivity': float(self.config.get('glitch_sensitivity', 0.65)),
            "text_speed": float(self.config.get("text_speed", 80.0)),
            'noise_intensity': float(self.config.get('noise_intensity', 0.6)),
            'zoom': float(self.config.get('zoom', 1.0)),
        }
        self._prog = self._make_program(_VERT, _FRAG)
        self._vao, self._vbo = self._fullscreen_quad(self._prog)
        self._beat = 0.0
        self._bass = 0.0
        self._mid = 0.0
        self._treble = 0.0
        # Startup variation so each activation is visually distinct at t=0.
        self._style_a = float(self.rng.uniform(0.0, 1.0))
        self._style_b = float(self.rng.uniform(0.0, 1.0))
        self.time = float(self.rng.uniform(0.0, 10_000.0))
        self._buffer_lines = []
        self._line_timer = 0.0

    def update(self, dt: float, audio: AudioData) -> None:
        super().update(dt, audio)
        self._bass = float(audio.bass_n)
        self._mid = float(audio.mid_n)
        self._treble = float(audio.treble_n)
        if audio.beat > 0.35:
            self._beat = 1.0
        speed = max(0.05, float(self.parameters['speed']))
        react = max(0.05, float(self.parameters['reactivity']))
        self._beat = max(0.0, self._beat - dt * (2.2 + speed * (0.6 + react * 0.2)))
        
        # Simulate terminal output growth
        self._line_timer += dt
        interval = 0.32 / max(0.25, speed * (0.85 + react * 0.35) + self._mid * 0.8 + self._beat * 1.1)
        if self._line_timer > max(0.05, interval):
            self._line_timer = 0.0
            line = self._generate_log_line()
            self._buffer_lines.append(line)
            if len(self._buffer_lines) > 20:
                self._buffer_lines.pop(0)

    def _generate_log_line(self) -> str:
        """Generate a pseudo-random terminal log line."""
        prefixes = [
            "[INFO]",
            "[WARN]",
            "[ERROR]",
            "[DEBUG]",
            "[TRACE]",
            ">>>",
            "$",
            "#",
        ]
        messages = [
            "Scanning network...",
            "Encryption key found",
            "Firewall bypassed",
            "Connection established",
            "Data transfer: 92%",
            "Signal jammed",
            "Intrusion detected",
            "System reboot initiated",
            "Packets intercepted",
            "Protocol mismatch",
        ]
        return random.choice(prefixes) + " " + random.choice(messages)

    def render(self) -> None:
        self._prog["iTime"].value = self.time
        self._prog['iBass'].value = self._bass
        self._prog['iMid'].value = self._mid
        self._prog["iBeat"].value = self._beat
        self._prog["iTreble"].value = self._treble
        self._prog['iSpeed'].value = float(self.parameters['speed'])
        self._prog['iReactivity'].value = float(self.parameters['reactivity'])
        self._prog['iGlitchSensitivity'].value = float(self.parameters['glitch_sensitivity'])
        self._prog['iStyleA'].value = self._style_a
        self._prog['iStyleB'].value = self._style_b
        self._prog["iZoom"].value = float(self.parameters['zoom'])
        self._vao.render(moderngl.TRIANGLE_STRIP)

    def destroy(self) -> None:
        self._vao.release()
        self._vbo.release()
        self._prog.release()
