"""OpenArm executor: a deployed plan runs our end-to-end policy with scripts/grasp.sh.

Our policy (ACT or pi0.5, trained on teleoperation) does the whole task in one go, not one catalog
skill per step: run_plan() runs it once for the job and reports that attempt on every step. It
runs on the robot VM, next to the CAN bus and the cameras, as `runner.py --openarm --model MODEL`:

    grasp.sh MODEL [--remote SPACE] --max-time T   (preflight, GO in this terminal, policy, hold)

The terminal stays the robot's: GO starts it, Enter stops it or releases torque at the end,
Ctrl+C stops it at once. Success = the policy settled at the end pose on its own; Enter, the
max time, a safety stop or an aborted start count as failures.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

from .executor import Outcome

REPO = Path(__file__).resolve().parents[2]  # cocktail-robotics/


class OpenArmExecutor:
    supports_parallel = False
    end_to_end = True  # one policy run covers every step of the plan

    def __init__(self, model: str, remote: str | None = None, max_time: float = 60.0,
                 extra: list[str] | None = None) -> None:
        self.model, self.remote, self.max_time = model, remote, max_time
        self.extra = extra or []
        self.proc: subprocess.Popen | None = None

    def connect(self) -> None:
        if not (REPO / "scripts" / "grasp.sh").exists():
            raise RuntimeError(f"{REPO}/scripts/grasp.sh not found: run the runner on the robot VM")

    def load(self, step: dict[str, Any]) -> None:
        return

    def run_plan(self, job: dict[str, Any]) -> Outcome:
        cmd = [str(REPO / "scripts" / "grasp.sh"), self.model, "--max-time", f"{self.max_time:g}", *self.extra]
        if self.remote:
            cmd += ["--remote", self.remote]
        print(f"    policy {self.model}{' on ' + self.remote if self.remote else ' (local CPU)'}")
        t0 = time.time()
        # stdin is the terminal's (GO, Enter); stdout is echoed as it comes, prompts without a newline
        # included, and read line by line for the outcome.
        self.proc = subprocess.Popen(cmd, cwd=REPO, stdout=subprocess.PIPE,
                                     env={**os.environ, "PYTHONUNBUFFERED": "1"})
        reason, pending = "", ""
        while chunk := os.read(self.proc.stdout.fileno(), 4096):
            text = chunk.decode(errors="replace")
            print(text, end="", flush=True)
            *lines, pending = (pending + text).split("\n")
            for line in lines:
                line = line.strip()
                if line.startswith("Grasp done ("):
                    reason = line.split("(", 1)[1].split(")", 1)[0]
                elif line.startswith(("SAFETY STOP", "Aborted", "Preflight failed")):
                    reason = line
        code = self.proc.wait()
        self.proc = None
        ok = code == 0 and reason == "policy settled"
        return Outcome(ok, round(time.time() - t0, 1), f"end-to-end {self.model}: {reason or f'exit {code}'}")

    def run(self, step: dict[str, Any], timeout_s: float) -> Outcome:
        return self.run_plan({"steps": [step]})

    def home(self) -> None:
        return  # the policy ends at its own end pose, held until Enter in the robot terminal

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()  # run_policy.py turns SIGTERM into its Ctrl+C cleanup

    def close(self) -> None:
        self.stop()
