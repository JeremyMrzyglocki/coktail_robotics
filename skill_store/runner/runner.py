#!/usr/bin/env python3
"""Robot-side job runner.

Deliberately stdlib-only. mozrobot has to be installed outside the openpi uv
environment (Spirit's docs warn that mixing them breaks dependencies), so this
process must add nothing to that interpreter -- no httpx, no requests, no pydantic.

It only ever makes OUTBOUND requests. The API never connects to this laptop, so
there is no tunnel, no port forward and no firewall negotiation: this works behind
NAT, a captive portal, or a phone hotspot.

    python runner/runner.py --mock                 # no hardware
    python runner/runner.py --mock --speed 8       # fast rehearsal
    python runner/runner.py --robot --structure dualarm
    python runner/runner.py --openarm --model lleeoogg/act-cocktail-grasp-20261018-0415   # our OpenArm
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import signal
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runner.executor import MockExecutor, Outcome  # noqa: E402

# Set by the first Ctrl-C. An operator stop is not a skill failure: nothing more
# is reported, the arm is not sent home, and the runner exits after this job.
STOP = threading.Event()


def _never_arrived(exc: BaseException) -> bool:
    """True when the request certainly never reached the server (refused or
    unresolvable), so sending it again cannot record anything twice."""
    reason = getattr(exc, "reason", exc)
    return isinstance(reason, (ConnectionRefusedError, socket.gaierror))


def _retry(fn, *args, attempts: int = 3, idempotent: bool = True, **kw):
    """Call the API, riding out a short network blip. Raises if it never answers.

    A run report is not idempotent: after a timeout the row may already be
    written, and a second send would count the attempt twice in the ratings. So
    a non-idempotent call is only retried when the request never arrived."""
    for n in range(attempts):
        try:
            return fn(*args, **kw)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if n == attempts - 1 or (not idempotent and not _never_arrived(exc)):
                raise
            time.sleep(0.5 * 2 ** n)


class Api:
    def __init__(self, base: str, token: str) -> None:
        self.base = base.rstrip("/")
        self.token = token

    def _call(self, method: str, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            self.base + path, data=data, method=method,
            headers={
                "authorization": f"Bearer {self.token}",
                "content-type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read()
        return json.loads(body) if body else {}

    def next_job(self) -> dict | None:
        return self._call("GET", "/api/jobs/next").get("job")

    def report(self, **kw) -> None:
        self._call("POST", "/api/runs", kw)

    def complete(self, plan_id: int, status: str) -> None:
        self._call("POST", "/api/plans/complete", {"plan_id": plan_id, "status": status})


def build_executor(args) -> object:
    if args.mock:
        return MockExecutor(seed=args.seed, speed=args.speed)
    if args.openarm:
        from runner.openarm import OpenArmExecutor  # noqa: PLC0415

        ex = OpenArmExecutor(args.model, remote=args.remote, max_time=args.max_time,
                             extra=shlex.split(args.grasp_args))
        ex.connect()
        return ex
    from runner.moz1 import Moz1Executor  # noqa: PLC0415

    ex = Moz1Executor(structure=args.structure)
    ex.connect()
    return ex


def run_step(api: Api, ex, step: dict, args, plan_id: int, robot_model: str,
             log) -> bool:
    """One step, with retries. Returns True if it eventually passed."""
    idx = step["step_index"]
    hand = step.get("hand") or "-"
    label = f"[{idx + 1}] {step['skill_id']}({hand})"
    timeout = float(step.get("est_duration_s", 12.0)) * args.timeout_factor

    for attempt in range(1, args.retries + 2):
        if STOP.is_set():
            return False
        try:
            ex.load(step)
            outcome: Outcome = ex.run(step, timeout)
        except Exception as exc:  # noqa: BLE001
            outcome = Outcome(False, 0.0, f"{type(exc).__name__}: {exc}")
        if STOP.is_set():
            log(f"  {label} stopped by operator")
            return False

        suffix = "" if attempt == 1 else f" retry {attempt - 1}"
        log(f"  {label}{suffix} {'PASS' if outcome.success else 'FAIL'} "
            f"{outcome.duration_s:.1f}s {outcome.notes}")
        # Every attempt is logged. Ratings are computed from these rows, so a
        # quietly dropped failure would inflate them.
        try:
            _retry(api.report, idempotent=False,
                   plan_id=plan_id, step_index=idx, skill_id=step["skill_id"],
                   robot_model=robot_model, success=outcome.success,
                   duration_s=outcome.duration_s, notes=outcome.notes)
        except Exception as exc:  # noqa: BLE001
            # The attempt happened; only its record is lost. Say so loudly.
            log(f"  {label} WARNING: could not report this attempt ({exc})")
        if outcome.success:
            return True
        if STOP.is_set():        # a stop that arrived while reporting: no homing
            return False
        ex.home()
    return False


def run_end_to_end(api: Api, ex, job: dict, args) -> bool:
    """One policy run for the whole plan (OpenArm: our policy does the task end to end). The
    attempt is reported on every step, so each skill's rating is that run's outcome."""
    plan_id = job["plan_id"]
    robot_model = job.get("robot_model") or args.robot_model
    print(f"\n=== plan {plan_id}: {job.get('task','')}")
    print(f"    {len(job['steps'])} steps: " + ", ".join(s["skill_id"] for s in job["steps"]))
    try:
        outcome: Outcome = ex.run_plan(job)
    except Exception as exc:  # noqa: BLE001
        outcome = Outcome(False, 0.0, f"{type(exc).__name__}: {exc}")
    print(f"=== plan {plan_id}: {'PASS' if outcome.success else 'FAIL'} {outcome.duration_s:.1f}s {outcome.notes}")
    if STOP.is_set():
        return False
    for step in job["steps"]:
        try:
            _retry(api.report, idempotent=False, plan_id=plan_id, step_index=step["step_index"],
                   skill_id=step["skill_id"], robot_model=robot_model, success=outcome.success,
                   duration_s=outcome.duration_s, notes=outcome.notes)
        except Exception as exc:  # noqa: BLE001
            print(f"    WARNING: could not report step {step['step_index'] + 1} ({exc})")
    try:
        _retry(api.complete, plan_id, "done" if outcome.success else "failed")
    except Exception as exc:  # noqa: BLE001
        print(f"    WARNING: could not mark plan {plan_id} finished ({exc})")
    return outcome.success


def run_job(api: Api, ex, job: dict, args) -> bool:
    if getattr(ex, "end_to_end", False):
        return run_end_to_end(api, ex, job, args)
    plan_id = job["plan_id"]
    robot_model = job.get("robot_model", args.robot_model)
    waves = job.get("waves") or [[s] for s in job["steps"]]
    parallel = getattr(ex, "supports_parallel", False) and not args.serial

    print(f"\n=== plan {plan_id}: {job.get('task','')}")

    # A step with no checkpoint has no policy to run. Executing it anyway (the
    # mock would) logs a success rate for a skill that was never performed, so
    # the whole job is refused before any motion starts.
    untrained = sorted({s["skill_id"] for s in job["steps"] if not s.get("checkpoint")})
    if untrained:
        print(f"    refused: no checkpoint for {', '.join(untrained)} -- nothing run")
        _retry(api.complete, plan_id, "failed")
        return False

    print(f"    {len(job['steps'])} steps in {len(waves)} waves, "
          f"widest {job.get('max_parallel', 1)} "
          f"({'parallel' if parallel else 'sequential'})")
    if not parallel and job.get("max_parallel", 1) > 1:
        why = "--serial" if args.serial else f"{type(ex).__name__} cannot drive two skills at once"
        print(f"    note: running waves in order ({why})")

    print_lock = threading.Lock()

    def log(line: str) -> None:
        with print_lock:
            print(line, flush=True)

    all_ok = True
    t_start = time.time()
    serial_time = 0.0

    for w, wave in enumerate(waves, 1):
        log(f"  -- wave {w}/{len(waves)}")
        t_wave = time.time()
        results: dict[int, bool] = {}

        if parallel and len(wave) > 1:
            threads = []
            for step in wave:
                def work(st=step):
                    ok = False
                    try:
                        ok = run_step(api, ex, st, args, plan_id, robot_model, log)
                    except Exception as exc:  # noqa: BLE001
                        log(f"  [{st['step_index'] + 1}] crashed: {exc}")
                    results[st["step_index"]] = ok
                t = threading.Thread(target=work, daemon=True)
                t.start()
                threads.append(t)
            for t in threads:
                t.join()
        else:
            for step in wave:
                results[step["step_index"]] = run_step(
                    api, ex, step, args, plan_id, robot_model, log)

        # What this wave would have cost one step after another.
        serial_time += sum(float(s.get("est_duration_s", 12.0)) for s in wave) / max(
            args.speed if args.mock else 1.0, 0.01)

        # A step with no result (its thread died) failed; never count it as passed.
        failed = [s["step_index"] + 1 for s in wave if not results.get(s["step_index"])]
        if failed:
            why = "stopped by operator" if STOP.is_set() else f"failed at step(s) {failed}"
            log(f"  wave {w} {why} -- aborting plan")
            all_ok = False
            break
        log(f"  -- wave {w} done in {time.time() - t_wave:.1f}s")

    wall = time.time() - t_start
    if not STOP.is_set():
        ex.home()          # never move the arm after the operator said stop
    try:
        _retry(api.complete, plan_id, "done" if all_ok else "failed")
    except Exception as exc:  # noqa: BLE001
        print(f"    WARNING: could not mark plan {plan_id} finished ({exc}); "
              "the server fails it after its stale-run timeout")
    print(f"=== plan {plan_id}: {'done' if all_ok else 'failed'} in {wall:.1f}s")
    if parallel and serial_time > 0:
        saved = max(0.0, 1 - wall / serial_time)
        print(f"    {wall:.1f}s wall clock vs {serial_time:.1f}s if run one by one "
              f"({saved * 100:.0f}% faster)")
    return all_ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=os.environ.get("SKILLSTORE_API", "http://127.0.0.1:8000"))
    ap.add_argument("--token", default=os.environ.get("ROBOT_SHARED_SECRET", ""))
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true", help="no hardware (default)")
    mode.add_argument("--robot", action="store_true", help="drive a real Moz1")
    mode.add_argument("--openarm", action="store_true",
                      help="our OpenArm: every plan runs --model end to end with scripts/grasp.sh")
    ap.add_argument("--model", help="--openarm: policy (Hub repo id, OWNER/REPO/SUBFOLDER or local dir)")
    ap.add_argument("--remote", help="--openarm: run the policy on this GPU Space (scripts/remote_policy.py)")
    ap.add_argument("--max-time", type=float, default=60.0, help="--openarm: policy time limit, s")
    ap.add_argument("--grasp-args", default="", help='--openarm: more grasp.sh options, e.g. --grasp-args=--sim')
    ap.add_argument("--robot-model", default=None, help="default: Spirit AI Moz1, or OpenArm v10 with --openarm")
    ap.add_argument("--structure", default="dualarm")
    ap.add_argument("--retries", type=int, default=1,
                    help="extra attempts per step before the plan aborts")
    ap.add_argument("--timeout-factor", type=float, default=2.5)
    ap.add_argument("--speed", type=float, default=1.0, help="mock only")
    ap.add_argument("--seed", type=int, default=7, help="mock only")
    ap.add_argument("--poll", type=float, default=0.5)
    ap.add_argument("--once", action="store_true", help="run one job then exit")
    ap.add_argument("--serial", action="store_true",
                    help="force one step at a time, to measure against parallel")
    args = ap.parse_args()
    if not args.robot and not args.openarm:
        args.mock = True
    if args.openarm and not args.model:
        ap.error("--openarm needs --model")
    args.robot_model = args.robot_model or ("OpenArm v10" if args.openarm else "Spirit AI Moz1")

    if not args.token:
        print("ROBOT_SHARED_SECRET is not set -- the API will reject this runner.")
        return 2

    api = Api(args.api, args.token)
    ex = build_executor(args)

    def handle_sigint(signum, frame):  # noqa: ARG001
        if STOP.is_set():
            raise KeyboardInterrupt      # second Ctrl-C: leave now
        print("\nstopping: no further steps, no homing (Ctrl-C again to quit at once)")
        STOP.set()
        ex.stop()
    signal.signal(signal.SIGINT, handle_sigint)

    mode_label = ("MOCK" if args.mock else f"OPENARM ({args.model})" if args.openarm
                  else f"MOZ1 ({args.structure})")
    print(f"runner up [{mode_label}] -> {args.api}, polling every {args.poll}s")
    try:
        while not STOP.is_set():
            try:
                job = api.next_job()
            except urllib.error.HTTPError as exc:
                print(f"api {exc.code}: {exc.reason}")
                time.sleep(2.0)
                continue
            except urllib.error.URLError as exc:
                print(f"api unreachable ({exc.reason}); retrying")
                time.sleep(2.0)
                continue

            if job is None:
                if args.once:
                    print("no queued job")
                    return 0
                time.sleep(args.poll)
                continue

            try:
                run_job(api, ex, job, args)
            except Exception as exc:  # noqa: BLE001
                print(f"plan {job.get('plan_id')} crashed: {type(exc).__name__}: {exc}")
                try:
                    _retry(api.complete, job["plan_id"], "failed")
                except Exception:  # noqa: BLE001
                    pass             # the server's stale-run timeout catches it
            if args.once:
                return 0
        print("stopped.")
        return 0
    except KeyboardInterrupt:
        print("\nquit.")
        return 130
    finally:
        ex.close()


if __name__ == "__main__":
    raise SystemExit(main())
