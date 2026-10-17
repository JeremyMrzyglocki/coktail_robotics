"""The robot side. A lost report must never turn a failed step into a pass, and
an operator's stop must stop: no more motion, no fake failures in the ratings."""
import argparse
import urllib.error

import pytest

from runner import runner
from runner.executor import Outcome


class FakeApi:
    def __init__(self, drop_report_for=()):
        self.reports, self.completed = [], []
        self.drop = set(drop_report_for)

    def report(self, **kw):
        if kw["step_index"] in self.drop:
            raise urllib.error.URLError("network blip")
        self.reports.append((kw["step_index"], kw["success"]))

    def complete(self, plan_id, status):
        self.completed.append((plan_id, status))


class FakeExecutor:
    supports_parallel = True

    def __init__(self, fail=(), stop_after=None):
        self.fail, self.stop_after, self.homes, self.ran = set(fail), stop_after, 0, []

    def load(self, step):
        pass

    def run(self, step, timeout):
        self.ran.append(step["step_index"])
        if self.stop_after is not None and len(self.ran) > self.stop_after:
            runner.STOP.set()
            return Outcome(False, 0.0, "stopped")
        return Outcome(step["step_index"] not in self.fail, 0.01, "")

    def home(self):
        self.homes += 1

    def stop(self):
        runner.STOP.set()


def args(**kw):
    base = dict(retries=0, timeout_factor=1.0, speed=1.0, mock=True, serial=False,
                robot_model="test")
    base.update(kw)
    return argparse.Namespace(**base)


def job(waves):
    steps = [s for w in waves for s in w]
    return {"plan_id": 1, "steps": steps, "waves": waves, "max_parallel": 2}


def step(i):
    return {"step_index": i, "skill_id": f"s{i}", "checkpoint": "ckpt", "est_duration_s": 1}


@pytest.fixture(autouse=True)
def clear_stop(monkeypatch):
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)
    runner.STOP.clear()
    yield
    runner.STOP.clear()


def test_a_failed_parallel_step_with_a_lost_report_still_fails_the_plan():
    api, ex = FakeApi(drop_report_for={1}), FakeExecutor(fail={1})
    ok = runner.run_job(api, ex, job([[step(0), step(1)], [step(2)]]), args())
    assert ok is False and api.completed == [(1, "failed")]
    assert 2 not in ex.ran                       # the next wave never started


def test_a_crashing_step_thread_counts_as_failed(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("thread died")
    monkeypatch.setattr(runner, "run_step", boom)
    ok = runner.run_job(FakeApi(), FakeExecutor(), job([[step(0), step(1)]]), args())
    assert ok is False


def test_operator_stop_reports_nothing_and_never_homes():
    api, ex = FakeApi(), FakeExecutor(stop_after=1)
    ok = runner.run_job(api, ex, job([[step(0)], [step(1)], [step(2)]]), args(retries=2))
    assert ok is False
    assert api.reports == [(0, True)]            # the stop itself is not a skill failure
    assert ex.homes == 0 and ex.ran == [0, 1]


def test_a_clean_plan_passes_and_homes_once():
    api, ex = FakeApi(), FakeExecutor()
    assert runner.run_job(api, ex, job([[step(0), step(1)], [step(2)]]), args())
    assert sorted(api.reports) == [(0, True), (1, True), (2, True)]
    assert ex.homes == 1 and api.completed == [(1, "done")]


def test_a_report_that_timed_out_is_not_sent_twice():
    calls = []

    def slow_report(**kw):
        calls.append(kw)
        raise urllib.error.URLError(TimeoutError("read timed out"))
    with pytest.raises(urllib.error.URLError):
        runner._retry(slow_report, idempotent=False, plan_id=1)
    assert len(calls) == 1


def test_a_refused_report_is_retried():
    calls = []

    def refused(**kw):
        calls.append(kw)
        if len(calls) < 2:
            raise urllib.error.URLError(ConnectionRefusedError())
    runner._retry(refused, idempotent=False, plan_id=1)
    assert len(calls) == 2


def test_a_stop_during_the_report_means_no_homing():
    class StopsWhileReporting(FakeApi):
        def report(self, **kw):
            runner.STOP.set()
            super().report(**kw)
    ex = FakeExecutor(fail={0})
    runner.run_step(StopsWhileReporting(), ex, step(0), args(retries=2), 1, "m", print)
    assert ex.homes == 0
