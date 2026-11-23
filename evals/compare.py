"""Compare two eval runs: what got better, what got worse.

    python -m evals.compare results/<baseline_run> results/<candidate_run>

A higher overall score can still hide regressions, so this lists every case that
got worse, not just the headline number.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .report import summarize


def load_run(run_dir: Path | str) -> tuple[dict, list[dict]]:
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    with open(run_dir / "results.jsonl", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return meta, rows


def _delta(a: float, b: float) -> str:
    d = round((b - a) * 100)
    if d == 0:
        return "0"
    return f"{'+' if d > 0 else ''}{d} pts {'🟢' if d > 0 else '🔴'}"


def build_comparison(meta_a: dict, rows_a: list[dict], meta_b: dict, rows_b: list[dict]) -> str:
    a, b = summarize(rows_a), summarize(rows_b)
    A, B = meta_a["name"], meta_b["name"]
    out = [f"# Comparison: `{A}` → `{B}`\n"]

    if meta_a.get("mock") or meta_b.get("mock"):
        out.append("> **Includes a MOCK RUN.** These numbers mean nothing.\n")
    warnings = []
    for key in ["cases_file", "policy_hash", "judge_model"]:
        if meta_a.get(key) != meta_b.get(key):
            warnings.append(f"`{key}` differs ({meta_a.get(key)} vs {meta_b.get(key)})")
    if warnings:
        out.append("> ⚠️ Not a like-for-like comparison: " + "; ".join(warnings) + "\n")

    out.append("| | Baseline | Candidate |\n|---|---|---|")
    for key in ["prompt_file", "model", "judge_model", "trials"]:
        out.append(f"| {key} | `{meta_a.get(key)}` | `{meta_b.get(key)}` |")
    out.append("")

    out.append("## Headline\n")
    out.append("| | Baseline | Candidate | Change |\n|---|---:|---:|---:|")
    out.append(f"| **Overall** | {a['pass_rate']:.0%} | {b['pass_rate']:.0%} | {_delta(a['pass_rate'], b['pass_rate'])} |")
    for cat in sorted(set(a["by_category"]) | set(b["by_category"])):
        ra = a["by_category"].get(cat, {}).get("pass_rate")
        rb = b["by_category"].get(cat, {}).get("pass_rate")
        if ra is None or rb is None:
            out.append(f"| {cat} | {'–' if ra is None else f'{ra:.0%}'} | {'–' if rb is None else f'{rb:.0%}'} | |")
        else:
            out.append(f"| {cat} | {ra:.0%} | {rb:.0%} | {_delta(ra, rb)} |")
    out.append("")

    out.append("## By check\n")
    out.append("| Check | Baseline | Candidate | Change |\n|---|---:|---:|---:|")
    for name in sorted(set(a["by_check"]) | set(b["by_check"])):
        ra = a["by_check"].get(name, {}).get("pass_rate")
        rb = b["by_check"].get(name, {}).get("pass_rate")
        if ra is not None and rb is not None:
            out.append(f"| {name} | {ra:.0%} | {rb:.0%} | {_delta(ra, rb)} |")
    out.append("")

    shared = sorted(set(a["by_case"]) & set(b["by_case"]))
    regressions = [c for c in shared if b["by_case"][c] < a["by_case"][c]]
    improvements = [c for c in shared if b["by_case"][c] > a["by_case"][c]]

    fail_reasons = {}
    for r in rows_b:
        if not r["passed"]:
            reasons = [f"{c['name']}: {c['detail']}" for c in r.get("checks", []) if not c["passed"]]
            if r.get("error"):
                reasons.append(f"error: {r['error']}")
            fail_reasons.setdefault(r["case_id"], reasons)

    out.append(f"## Regressions ({len(regressions)})\n")
    out.append("Cases that did worse in the candidate. Read these before shipping, even if the headline went up.\n")
    if not regressions:
        out.append("None.\n")
    for c in regressions:
        out.append(f"- **`{c}`**: {a['by_case'][c]:.0%} → {b['by_case'][c]:.0%}")
        for reason in fail_reasons.get(c, []):
            out.append(f"  - {reason}")
    out.append("")

    out.append(f"## Improvements ({len(improvements)})\n")
    if not improvements:
        out.append("None.\n")
    for c in improvements:
        out.append(f"- `{c}`: {a['by_case'][c]:.0%} → {b['by_case'][c]:.0%}")
    out.append("")

    still_failing = [c for c in shared if b["by_case"][c] == a["by_case"][c] < 1]
    if still_failing:
        out.append(f"## Still failing in both ({len(still_failing)})\n")
        out.append(", ".join(f"`{c}`" for c in still_failing) + "\n")

    return "\n".join(out)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("baseline")
    p.add_argument("candidate")
    p.add_argument("--out", help="Write the comparison here (default: <candidate>/comparison.md)")
    args = p.parse_args(argv)

    meta_a, rows_a = load_run(args.baseline)
    meta_b, rows_b = load_run(args.candidate)
    md = build_comparison(meta_a, rows_a, meta_b, rows_b)
    out = Path(args.out) if args.out else Path(args.candidate) / "comparison.md"
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
