"""Thin wrappers around the model API, plus offline mocks for testing the pipeline."""
from __future__ import annotations

import json
import os
import time
from typing import Protocol

DEFAULT_BOT_MODEL = os.environ.get("EVAL_MODEL", "claude-haiku-5-5")
DEFAULT_JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "claude-sonnet-5-5")


class Model(Protocol):
    name: str

    def complete(self, system: str, user: str, max_tokens: int = 1024,
                 temperature: float | None = None) -> str: ...


class AnthropicModel:
    def __init__(self, name: str):
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover
            raise SystemExit("Install dependencies first: pip install -r requirements.txt") from e
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key, "
                "or run with --mock to test the pipeline without an API key."
            )
        self.name = name
        # The SDK retries rate-limit and server errors with backoff.
        self._client = anthropic.Anthropic(max_retries=5)

    def complete(self, system: str, user: str, max_tokens: int = 1024,
                 temperature: float | None = None) -> str:
        kwargs = dict(
            model=self.name,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if temperature is not None:
            kwargs["temperature"] = temperature
        resp = self._client.messages.create(**kwargs)
        return "".join(block.text for block in resp.content if block.type == "text").strip()


class MockBot:
    """Deterministic fake assistant. Only for checking that the pipeline runs end to end.

    Its answers are deliberately generic, so a mock run's scores mean nothing.
    """

    name = "mock-bot"

    def complete(self, system: str, user: str, max_tokens: int = 1024,
                 temperature: float | None = None) -> str:
        time.sleep(0.01)
        text = user.lower()
        if "real person" in text or "chargeback" in text:
            return "I'm sorry for the trouble. Let me connect you with a member of our team.\n[ESCALATE]"
        return ("Thanks for reaching out! Most items can be returned within 30 days of delivery "
                "at kestrelhome.example/returns. (This is a mock response.)")


class MockJudge:
    """Fake judge that passes everything. Only for pipeline tests."""

    name = "mock-judge"

    def complete(self, system: str, user: str, max_tokens: int = 1024,
                 temperature: float | None = None) -> str:
        verdict = {"reason": "Mock judge: no real grading happened.", "pass": True}
        return json.dumps({"accuracy": verdict, "helpfulness": verdict, "tone": verdict})


def make_models(bot_model: str, judge_model: str, mock: bool) -> tuple[Model, Model]:
    if mock:
        return MockBot(), MockJudge()
    return AnthropicModel(bot_model), AnthropicModel(judge_model)
