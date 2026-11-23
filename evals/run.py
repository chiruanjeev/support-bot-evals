"""Run the eval suite against one prompt version.

Examples:
    python -m evals.run --prompt prompts/v1_baseline.txt
    python -m evals.run --prompt prompts/v2_improved.txt --trials 3
    python -m evals.run --prompt prompts/v2_improved.txt --category edge_case --category escalation
    python -m evals.run --prompt prompts/v2_improved.txt --mock   # no API key needed
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from . import data
from .graders import run_code_checks
from .judge import judge_response
from .models import DEFAULT_BOT_MODEL, DEFAULT_JUDGE_MODEL, make_models
from .report import build_report, summarize

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional
    pass


def run_one(case: dict, trial: int, bot, judge, system_prompt: str, policy: str,
            bot_temperature: float | None, judge_temperature: float | None) -> dict:
    user_message = data.build_user_message(case)
    row = {
        "case_id": case["id"],
        "category": case["category"],
        "trial": trial,
        "input": case["input"],
        "order": case.get("order"),
        "rubric": case.get("rubric", ""),
    }
    start = time.time()
    try:
        response = bot.complete(system_prompt, user_message, max_tokens=1024, temperature=bot_temperature)
    except Exception as e:
        row.update(response=None, error=f"{type(e).__name__}: {e}", checks=[], passed=False,
                   latency_s=round(time.time() - start, 2))
        return row
    row["latency_s"] = round(time.time() - start, 2)
    row["response"] = response

    checks = run_code_checks(case, response)
    judge_checks, judge_error = judge_response(
        judge, policy, user_message, case.get("rubric", ""), response, temperature=judge_temperature
    )
    checks += judge_checks
    row["checks"] = [c.to_dict() for c in checks]
    row["judge_error"] = judge_error
    row["error"] = None
    row["passed"] = all(c.passed for c in checks)
    return row


def main(argv: list[str] | None = None) -> Path:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prompt", required=True, help="Prompt template file (uses {policy} placeholder)")
    p.add_argument("--cases", default=str(data.DATA_DIR / "test_cases.jsonl"))
    p.add_argument("--policy", default=str(data.DATA_DIR / "policy.md"))
    p.add_argument("--model", default=DEFAULT_BOT_MODEL, help=f"Model under test (default {DEFAULT_BOT_MODEL})")
    p.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL, help=f"Judge model (default {DEFAULT_JUDGE_MODEL})")
    p.add_argument("--temperature", type=float, default=None, help="Bot temperature (default: model default)")
    p.add_argument("--judge-temperature", type=float, default=0.0)
    p.add_argument("--trials", type=int, default=1, help="Run each case N times to measure consistency")
    p.add_argument("--category", action="append", choices=data.CATEGORIES, help="Only run these categories")
    p.add_argument("--case", action="append", dest="case_ids", help="Only run these case ids")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--name", help="Run name (default: <prompt>_<timestamp>)")
    p.add_argument("--out-dir", default="results")
    p.add_argument("--mock", action="store_true", help="Use fake models to test the pipeline offline")
    args = p.parse_args(argv)

    cases = data.load_cases(args.cases)
    if args.category:
        cases = [c for c in cases if c["category"] in args.category]
    if args.case_ids:
        cases = [c for c in cases if c["id"] in args.case_ids]
    if not cases:
        raise SystemExit("No test cases selected.")

    policy = data.load_policy(args.policy)
    system_prompt = data.build_system_prompt(args.prompt, policy)
    bot, judge = make_models(args.model, args.judge_model, args.mock)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    name = args.name or f"{Path(args.prompt).stem}{'_mock' if args.mock else ''}_{stamp}"
    run_dir = Path(args.out_dir) / name
    run_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "name": name,
        "timestamp_utc": stamp,
        "prompt_file": str(args.prompt),
        "prompt_hash": data.short_hash(system_prompt),
        "cases_file": str(args.cases),
        "policy_hash": data.short_hash(policy),
        "model": bot.name,
        "judge_model": judge.name,
        "temperature": args.temperature,
        "judge_temperature": args.judge_temperature,
        "trials": args.trials,
        "num_cases": len(cases),
        "mock": args.mock,
    }

    jobs = [(c, t) for c in cases for t in range(1, args.trials + 1)]
    print(f"Running {len(cases)} cases x {args.trials} trial(s) = {len(jobs)} runs  [{bot.name}, judge: {judge.name}]")
    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(run_one, c, t, bot, judge, system_prompt, policy, args.temperature, args.judge_temperature)
            for c, t in jobs
        ]
        for i, fut in enumerate(as_completed(futures), 1):
            row = fut.result()
            rows.append(row)
            mark = "ERR " if row.get("error") else ("pass" if row["passed"] else "FAIL")
            print(f"  [{i:>3}/{len(jobs)}] {mark}  {row['case_id']} (trial {row['trial']})")

    order = {c["id"]: i for i, c in enumerate(cases)}
    rows.sort(key=lambda r: (order[r["case_id"]], r["trial"]))

    with open(run_dir / "results.jsonl", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (run_dir / "report.md").write_text(build_report(meta, rows), encoding="utf-8")

    s = summarize(rows)
    print(f"\nPass rate: {s['passed']}/{s['total']} ({s['pass_rate']:.0%})", end="")
    print(f"   errors: {s['errors']}" if s["errors"] else "")
    for cat, cs in s["by_category"].items():
        print(f"  {cat:<20} {cs['passed']:>3}/{cs['total']:<3} {cs['pass_rate']:.0%}")
    print(f"\nReport: {run_dir / 'report.md'}")
    return run_dir


if __name__ == "__main__":
    main()
