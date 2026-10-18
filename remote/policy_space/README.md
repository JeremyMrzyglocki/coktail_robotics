---
title: Cocktail policy server
emoji: 🍸
colorFrom: indigo
colorTo: pink
sdk: docker
app_port: 7860
pinned: false
---

GPU policy server of the cocktail robot (LeRobot policy, e.g. π0.5). Deployed and driven by
`scripts/remote_policy.py` of github.com/antonin-leroy/coktail_robotics; the policy repo comes from
the `POLICY` variable, gated models (π0.5's PaliGemma tokenizer) from the `HF_TOKEN` secret.

- `GET /health`: `{"state": "loading" | "ready" | "error", ...}`
- `GET /info`: policy, features, chunk size
- `POST /act` `{"state": [...], "images": {"front": "<base64 JPEG>", ...}, "task": "...", "robot_type": "..."}`
  → `{"actions": [[...], ...], "infer_ms": ...}`: the next `n_action_steps` actions, unnormalized.
