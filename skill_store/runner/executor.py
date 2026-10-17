"""The adapter boundary.

Everything above this file -- storefront, compiler, queue, ratings -- is written
against SkillExecutor and never touches robot hardware. That is what lets the web
work proceed while one person fights the SDK, and it is also the demo fallback:
run the whole system on MockExecutor and nothing upstream changes.
"""
from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class Outcome:
    success: bool
    duration_s: float
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class SkillExecutor(Protocol):
    supports_parallel: bool
    """True if two steps on different hands may be driven at the same time."""

    def load(self, step: dict[str, Any]) -> None:
        """Make the skill ready to run (select checkpoint, set the prompt)."""

    def run(self, step: dict[str, Any], timeout_s: float) -> Outcome:
        """Execute one skill to completion, failure, or timeout."""

    def home(self) -> None:
        """Return to the reset pose so the next trial starts identically."""

    def stop(self) -> None:
        """Halt immediately. Must be safe to call at any time."""

    def close(self) -> None:
        ...


class MockExecutor:
    """No hardware. Deterministic given a seed, so eval runs are reproducible.

    Per-skill success probabilities let you rehearse the demo -- including the
    retry path -- before you ever get robot time. It runs one thread per hand, so
    a balanced plan finishes in measurably less wall-clock time than a serial one.
    """

    supports_parallel = True

    DEFAULT_P = {
        "locate_object": 0.98,
        "grasp_bottle": 0.94,
        "grasp_bottle_lite": 0.72,
        "grasp_glass": 0.92,
        "grasp_cloth": 0.95,
        "release_object": 0.99,
        "move_to_station": 0.97,
        "place_on_coaster": 0.89,
        "pour_into": 0.84,
        "stir": 0.91,
        "wipe_surface": 0.88,
        "verify_surface_clean": 0.97,
    }

    def __init__(self, seed: int | None = 7, speed: float = 1.0,
                 probs: dict[str, float] | None = None) -> None:
        self.rng = random.Random(seed)
        self.speed = max(speed, 0.01)
        self.probs = {**self.DEFAULT_P, **(probs or {})}
        self._lock = threading.Lock()
        self._stopped = False

    def load(self, step: dict[str, Any]) -> None:
        # Nothing to warm up, and nothing shared -- safe to call from any thread.
        return

    def run(self, step: dict[str, Any], timeout_s: float) -> Outcome:
        dwell = min(step.get("est_duration_s", 8.0), timeout_s) / self.speed
        t0 = time.time()
        # Simulate work in slices so stop() is responsive.
        while time.time() - t0 < dwell and not self._stopped:
            time.sleep(0.05)
        if self._stopped:
            return Outcome(False, time.time() - t0, "stopped")
        p = self.probs.get(step["skill_id"], 0.8)
        with self._lock:          # random.Random is not thread safe
            ok = self.rng.random() < p
        hand = step.get("hand") or "-"
        return Outcome(ok, round(time.time() - t0, 2),
                       f"mock/{hand}" if ok else f"mock/{hand}: postcondition not reached")

    def home(self) -> None:
        time.sleep(0.2 / self.speed)

    def stop(self) -> None:
        self._stopped = True

    def close(self) -> None:
        pass
