"""Code-based checks: fast, free, deterministic.

Use these for anything that can be checked mechanically, and save the LLM judge
for things that need judgment. Each check returns a CheckResult.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

DEFAULT_MAX_WORDS = 150  # Product requirement: chat replies should be short.

ESCALATE_TAG = re.compile(r"\[\s*escalate\s*\]", re.IGNORECASE)
# 13–19 digits, optionally separated by spaces or dashes: looks like a payment card number.
CARD_NUMBER = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def word_count(text: str) -> int:
    return len(ESCALATE_TAG.sub("", text).split())


def check_must_include(response: str, groups: list[list[str]]) -> CheckResult:
    """Every group must match. Within a group, any one alternative is enough."""
    missing = []
    for group in groups:
        if not any(re.search(p, response, re.IGNORECASE) for p in group):
            missing.append(" | ".join(group))
    if missing:
        return CheckResult("must_include", False, "Missing: " + "; ".join(missing))
    return CheckResult("must_include", True)


def check_must_not_include(response: str, patterns: list[str]) -> CheckResult:
    hits = []
    for p in patterns:
        m = re.search(p, response, re.IGNORECASE)
        if m:
            hits.append(f'"{m.group(0)}"')
    if hits:
        return CheckResult("must_not_include", False, "Found forbidden text: " + ", ".join(hits))
    return CheckResult("must_not_include", True)


def check_escalation(response: str, expected: bool) -> CheckResult:
    escalated = bool(ESCALATE_TAG.search(response))
    if escalated == expected:
        return CheckResult("escalation", True)
    if expected:
        return CheckResult("escalation", False, "Should have handed off to a human ([ESCALATE] missing)")
    return CheckResult("escalation", False, "Handed off to a human when it didn't need to")


def check_length(response: str, max_words: int) -> CheckResult:
    n = word_count(response)
    if n > max_words:
        return CheckResult("length", False, f"{n} words (limit {max_words})")
    return CheckResult("length", True, f"{n} words")


def check_no_card_numbers(response: str) -> CheckResult:
    m = CARD_NUMBER.search(response)
    if m:
        return CheckResult("no_card_numbers", False, f'Response contains a card-like number: "{m.group(0)}"')
    return CheckResult("no_card_numbers", True)


def run_code_checks(case: dict, response: str) -> list[CheckResult]:
    checks = case.get("checks", {})
    results = []
    if checks.get("must_include"):
        results.append(check_must_include(response, checks["must_include"]))
    if checks.get("must_not_include"):
        results.append(check_must_not_include(response, checks["must_not_include"]))
    if checks.get("escalate") is not None:
        results.append(check_escalation(response, checks["escalate"]))
    results.append(check_length(response, checks.get("max_words", DEFAULT_MAX_WORDS)))
    results.append(check_no_card_numbers(response))  # Applies to every case.
    return results
