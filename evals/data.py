"""Loading test cases, the policy, and prompt templates."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

CATEGORIES = [
    "policy_lookup",
    "edge_case",
    "hallucination_trap",
    "escalation",
    "safety_privacy",
    "tone",
    "out_of_scope",
]


def load_cases(path: Path | str = DATA_DIR / "test_cases.jsonl") -> list[dict]:
    cases = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                case = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{line_no}: invalid JSON ({e})") from e
            case.setdefault("order", None)
            case.setdefault("checks", {})
            cases.append(case)
    return cases


def load_policy(path: Path | str = DATA_DIR / "policy.md") -> str:
    return Path(path).read_text(encoding="utf-8").strip()


def build_system_prompt(template_path: Path | str, policy: str) -> str:
    # str.replace rather than str.format so braces elsewhere in a prompt don't break it.
    return Path(template_path).read_text(encoding="utf-8").replace("{policy}", policy).strip()


def build_user_message(case: dict) -> str:
    """What the assistant sees: the customer's order (if any), then their message.

    In a real product the order details would come from a lookup tool or the CRM.
    """
    parts = []
    if case.get("order"):
        lines = [f"- {k.replace('_', ' ')}: {v}" for k, v in case["order"].items()]
        parts.append("<order_details>\n" + "\n".join(lines) + "\n</order_details>")
    parts.append("<customer_message>\n" + case["input"] + "\n</customer_message>")
    return "\n\n".join(parts)


def short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
