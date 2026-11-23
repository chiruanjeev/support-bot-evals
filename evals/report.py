"""Turns raw results into a Markdown report a PM can actually read."""
from __future__ import annotations

from collections import defaultdict


def _pct(n: int, d: int) -> str:
    return f"{n / d:.0%}" if d else "–"


def summarize(rows: list[dict]) -> dict:
    total = len(rows)
    passed = sum(r["passed"] for r in rows)
    errors = sum(1 for r in rows if r.get("error"))
    judge_errors = sum(1 for r in rows if r.get("judge_error"))

    by_cat: dict[str, list] = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r["passed"])

    by_check: dict[str, list] = defaultdict(list)
    for r in rows:
        for c in r.get("checks", []):
            by_check[c["name"]].append(c["passed"])

    by_case: dict[str, list] = defaultdict(list)
    for r in rows:
        by_case[r["case_id"]].append(r["passed"])

    return {
        "total": total,
        "passed": passed,
        "pass_rate": passed / total if total else 0.0,
        "errors": errors,
        "judge_errors": judge_errors,
        "by_category": {
            k: {"total": len(v), "passed": sum(v), "pass_rate": sum(v) / len(v)} for k, v in by_cat.items()
        },
        "by_check": {
            k: {"total": len(v), "failed": len(v) - sum(v), "pass_rate": sum(v) / len(v)} for k, v in by_check.items()
        },
        "by_case": {k: sum(v) / len(v) for k, v in by_case.items()},
        "flaky": sorted(k for k, v in by_case.items() if 0 < sum(v) < len(v)),
    }


def _quote(text: str | None, limit: int = 900) -> str:
    if not text:
        return "> _(no response)_"
    text = text if len(text) <= limit else text[:limit] + " …"
    return "\n".join("> " + line if line.strip() else ">" for line in text.splitlines())


def build_report(meta: dict, rows: list[dict]) -> str:
    s = summarize(rows)
    out = []
    out.append(f"# Eval report: `{meta['name']}`\n")
    if meta.get("mock"):
        out.append("> **MOCK RUN.** Fake model and fake judge, used only to test the pipeline. These scores mean nothing.\n")

    out.append("| | |\n|---|---|")
    for key in ["prompt_file", "prompt_hash", "model", "judge_model", "trials", "num_cases", "timestamp_utc"]:
        out.append(f"| {key} | `{meta.get(key)}` |")
    out.append("")

    out.append("## Summary\n")
    out.append(f"**Overall pass rate: {s['passed']}/{s['total']} ({s['pass_rate']:.0%})**  ")
    out.append("A run passes only if every code check and every judge dimension passes.\n")
    if s["errors"]:
        out.append(f"⚠️ {s['errors']} run(s) errored before grading (counted as failures).\n")
    if s["judge_errors"]:
        out.append(f"⚠️ {s['judge_errors']} judge call(s) failed or returned unreadable output (counted as failures).\n")

    out.append("### By category\n")
    out.append("| Category | Passed | Pass rate |\n|---|---:|---:|")
    for cat, cs in sorted(s["by_category"].items()):
        out.append(f"| {cat} | {cs['passed']}/{cs['total']} | {cs['pass_rate']:.0%} |")
    out.append("")

    out.append("### By check\n")
    out.append("Which kinds of failure are most common. Code checks are exact; `judge:*` rows come from the LLM judge.\n")
    out.append("| Check | Failures | Pass rate |\n|---|---:|---:|")
    for name, cs in sorted(s["by_check"].items(), key=lambda kv: -kv[1]["failed"]):
        out.append(f"| {name} | {cs['failed']}/{cs['total']} | {cs['pass_rate']:.0%} |")
    out.append("")

    if meta.get("trials", 1) > 1:
        out.append("### Consistency\n")
        if s["flaky"]:
            out.append("These cases passed on some trials and failed on others. Same input, different outcome:\n")
            for cid in s["flaky"]:
                out.append(f"- `{cid}`: passed {s['by_case'][cid]:.0%} of trials")
        else:
            out.append("Every case gave the same pass/fail result on every trial.")
        out.append("")

    failures = [r for r in rows if not r["passed"]]
    out.append(f"## Failures ({len(failures)})\n")
    if not failures:
        out.append("None. Time to write harder test cases.\n")
    for r in failures:
        trial = f", trial {r['trial']}" if meta.get("trials", 1) > 1 else ""
        out.append(f"### `{r['case_id']}` ({r['category']}{trial})\n")
        out.append(f"**Customer:** {r['input']}\n")
        if r.get("order"):
            details = "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in r["order"].items())
            out.append(f"**Order:** {details}\n")
        out.append(f"**Good answer:** {r.get('rubric', '')}\n")
        out.append("**Bot replied:**\n")
        out.append(_quote(r.get("response")) + "\n")
        if r.get("error"):
            out.append(f"- ❌ **error**: {r['error']}")
        for c in r.get("checks", []):
            if not c["passed"]:
                out.append(f"- ❌ **{c['name']}**: {c['detail']}")
        out.append("")

    return "\n".join(out)
