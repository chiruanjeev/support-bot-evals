"""End-to-end run with mock models: no API key, no cost."""
import json

from evals import calibrate, compare, run
from evals.calibrate import cohens_kappa
from evals.data import ROOT
from evals.judge import judge_response
from evals.models import MockJudge


def test_mock_run_compare_and_calibrate(tmp_path):
    a = run.main(["--prompt", str(ROOT / "prompts/v1_baseline.txt"), "--mock", "--out-dir", str(tmp_path), "--name", "a"])
    b = run.main(["--prompt", str(ROOT / "prompts/v2_improved.txt"), "--mock", "--out-dir", str(tmp_path), "--name", "b",
                  "--trials", "2", "--category", "escalation"])

    rows = [json.loads(line) for line in (a / "results.jsonl").read_text().splitlines()]
    assert len(rows) == 34
    assert all("checks" in r and "passed" in r for r in rows)
    assert "MOCK RUN" in (a / "report.md").read_text()
    assert json.loads((b / "meta.json").read_text())["trials"] == 2

    compare.main([str(a), str(b)])
    assert "Regressions" in (b / "comparison.md").read_text()

    sheet = calibrate.export(a, n=4, seed=1)
    assert "judge" not in sheet.read_text(encoding="utf-8-sig").splitlines()[0]  # labeling stays blind


def test_judge_errors_are_recorded_not_hidden():
    class BrokenJudge:
        name = "broken"

        def complete(self, *args, **kwargs):
            return "I think this reply is fine!"

    results, err = judge_response(BrokenJudge(), "policy", "convo", "rubric", "reply")
    assert err and all(not r.passed for r in results)

    results, err = judge_response(MockJudge(), "policy", "convo", "rubric", "reply")
    assert err is None and all(r.passed for r in results)


def test_cohens_kappa():
    assert cohens_kappa([(True, True), (False, False)]) == 1.0
    assert cohens_kappa([(True, False), (False, True)]) < 0
    assert cohens_kappa([]) is None
