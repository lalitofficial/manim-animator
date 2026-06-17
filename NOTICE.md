# Third-party data & assets — attribution

This project derives data from third-party sources. Raw datasets are **not** committed
(see `.gitignore`); only **derived measurements** and **normalized assets** live in the repo,
each recorded here.

## Meta Amateur Drawings Dataset — MIT License

- Source: <https://github.com/facebookresearch/AnimatedDrawings> ·
  <https://ai.meta.com/blog/ai-dataset-animation-drawings/>
- Paper: *A Method for Animating Children's Drawings of the Human Figure* (SIGGRAPH 2023),
  Smith et al. — <https://arxiv.org/abs/2303.12741>
- License: **MIT** (code, model weights, and the Amateur Drawings dataset).
- Raw annotations (`amateur_drawings_annotations.json`, ~288MB) are downloaded locally to
  `backend/engine/assets/animateddrawings/` (**gitignored**) and used only by `tools/ad_mine.py`.
- **Committed, derived from it** (statistical measurements over ~178k figures, not the images):
  - `backend/engine/character_proportions.json` — median limb-length ratios.
  - `backend/engine/pose_library.json` — median rig limb-angles per named pose.

These derived files contain aggregate geometry only (no images, no per-drawing data) and drive the
deterministic vector character rig (`backend/engine/character.py`).

## Icon recipes (composed, original)

`icon_recipes.json`, `cartoon_recipes.json`, and the parametric families in
`backend/engine/families.py` are original compositions authored for this project. The vendored
Lucide (`assets/iconify/lucide.json`) and Tabler (`assets/tabler/`) line-icon sets are MIT-licensed.
