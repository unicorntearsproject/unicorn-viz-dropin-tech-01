"""
Cyber War — Real-time digital battle-map effect.
Offensive (red) nodes attack defensive (blue) nodes across a grid,
with audio-driven pulse waves and frequency-mapped node intensity.
"""
from __future__ import annotations

import math
import numpy as np
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
uniform float iTime;
uniform float iBass;
uniform float iMid;
uniform float iTreble;
uniform float iZoom;
uniform sampler2D iNodes;
in vec2 v_pos;
out vec4 fragColor;

float grid_dist(vec2 p) {
    vec2 grid = fract(p * 8.0);
    return min(grid.x, grid.y);
}

vec3 sample_node(vec2 uv) {
    return texture(iNodes, uv).rgb;
}

float pulse(float time, float freq) {
    return 0.5 + 0.5 * sin(time * freq);
}

vec3 palette(float t) {
    vec3 a = vec3(0.5, 0.5, 0.5);
    vec3 b = vec3(0.5, 0.5, 0.5);
    vec3 c = vec3(1.0, 1.0, 1.0);
    vec3 d = vec3(0.0, 0.1, 0.2);
    return a + b * cos(6.28318 * (c * t + d));
}

void main() {
    vec2 uv = v_pos;
    uv = (uv - 0.5) / max(iZoom, 0.01) + 0.5;
    vec2 grid_pos = uv * 16.0;
    
    // Base grid
    float grid = grid_dist(uv);
    float grid_lines = smoothstep(0.05, 0.0, grid) * 0.14;
    
    // Node sampling
    vec3 node_col = sample_node(uv);
    float is_node = length(node_col) > 0.1 ? 1.0 : 0.0;
    
    // Compute local node intensity based on FFT/beat
    float node_intensity = is_node * (iBass * 0.7 + iMid * 0.35 + iTreble * 0.15);
    node_intensity += pulse(iTime, 3.5 + iTreble * 5.0) * is_node * 0.45;
    
    // Attack/defense coloring with slow time-varying hue motion.
    float attack_pulse = pulse(iTime + node_col.r * 10.0, 4.0);
    float defense_pulse = pulse(iTime + node_col.g * 8.0, 3.0);
    vec3 attack_shift = palette(0.08 + iTime * 0.04);
    vec3 defense_shift = palette(0.46 + iTime * 0.03);
    
    vec3 attack_col = mix(vec3(0.8, 0.1, 0.1), vec3(1.0, 0.45, 0.18), attack_pulse);
    vec3 defense_col = mix(vec3(0.1, 0.4, 0.8), vec3(0.15, 0.85, 1.0), defense_pulse);
    attack_col = mix(attack_col, attack_shift, 0.22);
    defense_col = mix(defense_col, defense_shift, 0.22);

    // Node twinkle for a less static board.
    float twinkle = 0.65 + 0.35 * sin(iTime * 6.0 + dot(floor(uv * 64.0), vec2(0.23, 0.71)));
    node_intensity *= twinkle;
    
    vec3 col = mix(
        attack_col * node_col.r + defense_col * node_col.g,
        vec3(0.02, 0.01, 0.04) + grid_lines,
        1.0 - is_node * node_intensity
    );
    
    // Energy beams between nodes
    float beam_dist = abs(sin(grid_pos.x * 3.14) * sin(grid_pos.y * 3.14));
    float beam_intensity = (iBass * 0.8 + iMid * 0.4) * smoothstep(0.3, 0.0, beam_dist);

    col += vec3(0.2, 0.8, 1.0) * beam_intensity * 0.35;

    // Projectile lanes: red and blue dots shooting across the battlefield.
    float lane_a = smoothstep(0.10, 0.02, abs(fract(uv.y * 14.0) - 0.5));
    float lane_b = smoothstep(0.10, 0.02, abs(fract(uv.y * 14.0 + 0.35) - 0.5));
    float shot_a = smoothstep(0.08, 0.0, abs(fract(uv.x * 6.0 - iTime * (1.8 + iBass * 2.1)) - 0.5));
    float shot_b = smoothstep(0.08, 0.0, abs(fract(uv.x * 6.0 + iTime * (1.6 + iMid * 1.8)) - 0.5));
    float trail_a = smoothstep(0.30, 0.0, abs(fract(uv.x * 6.0 - iTime * (1.8 + iBass * 2.1)) - 0.5));
    float trail_b = smoothstep(0.30, 0.0, abs(fract(uv.x * 6.0 + iTime * (1.6 + iMid * 1.8)) - 0.5));

    vec3 red_shot = vec3(1.0, 0.30, 0.20) * lane_a * shot_a * (0.4 + 0.8 * iBass);
    vec3 blue_shot = vec3(0.20, 0.80, 1.0) * lane_b * shot_b * (0.4 + 0.8 * iMid);
    vec3 red_trail = vec3(1.0, 0.20, 0.15) * lane_a * trail_a * 0.14;
    vec3 blue_trail = vec3(0.20, 0.70, 1.0) * lane_b * trail_b * 0.14;

    col += red_shot + blue_shot + red_trail + blue_trail;
    
    fragColor = vec4(col, 1.0);
}
"""

class CyberWar(BaseEffect):
    NAME = "Cyber War"
    AUTHOR = "Autopilot"
    TAGS = ["tech", "network", "cyberpunk"]
    PING_PONG_FRIENDS = [
        'Tron Grid',
        'Hacker Terminal',
        'Escher',
        'Fireworks',
        'Hexy Stars',
        'Metaballs',
        'Particle Storm',
        'Plasma',
        'Wormhole',
        'Psychedelic',
        'Starfield',
        'Tunnel',
        'Kaleidoscope',
        'Unicorn Tears',
    ]

    def _init(self) -> None:
        self.parameters = {
            "node_density": 0.15,
            "attack_speed": float(self.config.get("attack_speed", 2.0)),
            "defense_strength": 1.2,
            "pulse_intensity": 1.0,
            'zoom': float(self.config.get('zoom', 1.0)),
        }
        self._prog = self._make_program(_VERT, _FRAG)
        self._vao, self._vbo = self._fullscreen_quad(self._prog)
        self._node_tex = self._create_node_texture()
        self._bass = 0.0
        self._mid = 0.0
        self._treble = 0.0

    def _create_node_texture(self) -> moderngl.Texture:
        """Generate a procedural network node map texture."""
        w, h = 256, 256
        data = np.zeros((h, w, 3), dtype=np.uint8)
        
        np.random.seed(42)  # Deterministic
        node_count = int(w * h * self.parameters["node_density"] / 1000)
        
        for _ in range(node_count):
            x = np.random.randint(0, w)
            y = np.random.randint(0, h)
            is_attack = np.random.rand() > 0.5
            
            if is_attack:
                data[y, x] = [200, 50, 30]  # Red/orange attack node
            else:
                data[y, x] = [30, 100, 200]  # Blue defense node
        
        tex = self.ctx.texture((w, h), 3, data.tobytes())
        tex.filter = moderngl.LINEAR, moderngl.LINEAR
        return tex

    def update(self, dt: float, audio: AudioData) -> None:
        super().update(dt, audio)
        self._bass = audio.bass_n
        self._mid = audio.mid_n
        self._treble = audio.treble_n

    def render(self) -> None:
        self._prog["iTime"].value = self.time
        self._prog["iBass"].value = self._bass
        self._prog["iMid"].value = self._mid
        self._prog["iTreble"].value = self._treble
        self._prog["iZoom"].value = float(self.parameters['zoom'])
        self._node_tex.use(location=0)
        self._prog["iNodes"].value = 0
        self._vao.render(moderngl.TRIANGLE_STRIP)

    def destroy(self) -> None:
        self._vao.release()
        self._vbo.release()
        self._prog.release()
        self._node_tex.release()
