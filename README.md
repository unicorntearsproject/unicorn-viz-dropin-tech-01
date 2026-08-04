# tech-01 — Unicorn Viz effect pack

**Version 0.9.1**


cyber / hacker / network visuals

## Changelog

- **0.9.1** — cyber_war: node board now randomized per instance via `self.rng` (was `np.random.seed(42)` — identical board every run, and the global reseed de-randomized every other legacy `np.random` consumer in the process).
- **0.9.0** — initial versioned release.
