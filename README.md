# tech-01 — Unicorn Viz effect pack

**Version 0.11.0**


cyber / hacker / network visuals

## Changelog

- **0.11.0** — Tron Grid's ray-march budget is a live `march_steps` parameter (8–256, default 64) on the config editor's Effects tab instead of a compiled-in constant.
- **0.10.0** — restore three precision-dead layers (float32 time→hash collapse past 2^23, per the 2026-08-03 audit): threat_matrix matrix rain rendered black, reactor_breach rising sparks were frozen static, hacker_terminal_v2 glitch row + treble sparkle were stuck — all time terms now mod()-wrapped pre-hash. hacker_terminal_v2 also dirty-flags its 2,400-int glyph upload (~2,500 Python objects/frame → only on content change).
- **0.9.1** — cyber_war: node board now randomized per instance via `self.rng` (was `np.random.seed(42)` — identical board every run, and the global reseed de-randomized every other legacy `np.random` consumer in the process).
- **0.9.0** — initial versioned release.
