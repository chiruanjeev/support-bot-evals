"""Check whether the LLM judge agrees with you.

An LLM judge is only useful if it grades the way a careful human would. This
script lets you label a sample of replies yourself, blind to the judge's verdicts,
then measures how often the judge agrees with you.

Step 1: export a labeling sheet (open it in Excel or Google Sheets)
    python -m evals.calibrate export results/<run> --n 20

Step 2: fill in human_accuracy / human_helpfulness / human_tone with pass or fail

Step 3: score the judge against your labels
    python -m evals.calibrate score results/<run>
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

from .compare import load_run
from .judge import DIMENSIONS

SHEET = "labeling_sheet.csv"


def export(run_dir: Path, n: int, seed: int) -> Path:
    _, rows = load_run(run_dir)
    rows = [r for r in rows if r.get("response") and not r.get("judge_error")]
    rng = random.Random(seed)
    # Sample passes and fails roughly evenly, so you see both kinds of judge mistake.
    judged_pass = [r for r in rows if all(c["passed"] for c in r["checks"] if c["name"].startswith("judge:"))]
    judged_fail = [r for r in rows if r not in judged_pass]
    half = n // 2
    picked = rng.sample(judged_fail, min(half, len(judged_fail)))
    picked += rng.sample(judged_pass, min(n - len(picked), len(judged_pass)))
    if len(picked) < n:  # Top up if one side ran short.
        rest = [r for r in rows if r not in picked]
        picked += rng.sample(rest, min(n - len(picked), len(rest)))
    rng.shuffle(picked)

    path = run_dir / SHEET
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig so Excel reads it cleanly
        w = csv.writer(f)
        w.writerow(["case_id", "trial", "category", "customer_message", "order_details", "what_good_looks_like",
                    "bot_reply"] + [f"human_{d}" for d in DIMENSIONS] + ["notes"])
        for r in picked:
            order = "; ".join(f"{k}: {v}" for k, v in (r.get("order") or {}).items())
            w.writerow([r["case_id"], r["trial"], r["category"], r["input"], order, r.get("rubric", ""),
                        r["response"]] + [""] * len(DIMENSIONS) + [""])
    print(f"Wrote {len(picked)} rows to {path}")
    print("Fill in each human_* column with 'pass' or 'fail' (judge verdicts are hidden on purpose),")
    print(f"then run: python -m evals.calibrate score {run_dir}")
    return path


def _parse_label(value: str) -> bool | None:
    v = (value or "").strip().lower()
    if v in ("pass", "p", "yes", "y", "1", "true"):
        return True
    if v in ("fail", "f", "no", "n", "0", "false"):
        return False
    return None


def cohens_kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    """Agreement corrected for chance. 1 = perfect, 0 = no better than chance."""
    n = len(pairs)
    if n == 0:
        return None
    observed = sum(h == j for h, j in pairs) / n
    p_h = sum(h for h, _ in pairs) / n
    p_j = sum(j for _, j in pairs) / n
    expected = p_h * p_j + (1 - p_h) * (1 - p_j)
    if expected == 1:
        return 1.0 if observed == 1 else 0.0
    return (observed - expected) / (1 - expected)


def score(run_dir: Path, labels_path: Path | None) -> str:
    _, rows = load_run(run_dir)
    judge = {(r["case_id"], int(r["trial"])): {c["name"]: c for c in r.get("checks", [])} for r in rows}
    labels_path = labels_path or run_dir / SHEET

    with open(labels_path, newline="", encoding="utf-8-sig") as f:
        labeled = list(csv.DictReader(f))

    out = [f"# Judge calibration: `{run_dir.name}`\n",
           "How often the LLM judge agreed with human labels, per dimension.\n",
           "| Dimension | Labeled | Agreement | Cohen's κ | Judge too lenient | Judge too strict |",
           "|---|---:|---:|---:|---:|---:|"]
    disagreements = []
    for dim in DIMENSIONS:
        pairs = []
        for row in labeled:
            human = _parse_label(row.get(f"human_{dim}", ""))
            key = (row["case_id"], int(row["trial"]))
            if human is None or key not in judge:
                continue
            check = judge[key][f"judge:{dim}"]
            pairs.append((human, check["passed"]))
            if human != check["passed"]:
                disagreements.append((dim, row, check))
        if not pairs:
            out.append(f"| {dim} | 0 | – | – | – | – |")
            continue
        agree = sum(h == j for h, j in pairs) / len(pairs)
        k = cohens_kappa(pairs)
        lenient = sum(1 for h, j in pairs if j and not h)
        strict = sum(1 for h, j in pairs if h and not j)
        out.append(f"| {dim} | {len(pairs)} | {agree:.0%} | {k:.2f} | {lenient} | {strict} |")

    out.append("\n**Too lenient** = judge passed a reply you failed. These are the dangerous ones: bad replies "
               "that would slip through. **Too strict** = judge failed a reply you passed.\n")
    out.append("Rough guide: aim for ≥85% agreement before trusting the judge's numbers. If it's lower, read the "
               "disagreements below and tighten the judge prompt (evals/judge.py) or the case rubrics.\n")

    if disagreements:
        out.append(f"## Disagreements ({len(disagreements)})\n")
        for dim, row, check in disagreements:
            human = "pass" if _parse_label(row[f"human_{dim}"]) else "fail"
            judge_v = "pass" if check["passed"] else "fail"
            out.append(f"### `{row['case_id']}` · {dim}: you said **{human}**, judge said **{judge_v}**\n")
            out.append(f"- Customer: {row['customer_message']}")
            out.append(f"- Judge's reason: {check['detail']}")
            if row.get("notes"):
                out.append(f"- Your notes: {row['notes']}")
            out.append("")

    md = "\n".join(out)
    (run_dir / "calibration.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"\nSaved to {run_dir / 'calibration.md'}")
    return md


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="Write a blind labeling sheet")
    e.add_argument("run_dir")
    e.add_argument("--n", type=int, default=20)
    e.add_argument("--seed", type=int, default=0)
    s = sub.add_parser("score", help="Compare your labels to the judge")
    s.add_argument("run_dir")
    s.add_argument("--labels", help=f"Labeled CSV (default: <run_dir>/{SHEET})")
    args = p.parse_args(argv)

    if args.cmd == "export":
        export(Path(args.run_dir), args.n, args.seed)
    else:
        score(Path(args.run_dir), Path(args.labels) if args.labels else None)


if __name__ == "__main__":
    main()
