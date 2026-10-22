"""A stand-in for the OpenAI client, so tests never call Token Factory."""

from __future__ import annotations

from types import SimpleNamespace


class FakeLLM:
    def __init__(self, script=None, default="{}", reasoning=None):
        self.script: dict[str, list] = script or {}
        self.default = default
        self.reasoning = reasoning
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        queue = self.script.get(kw["model"])
        item = queue.pop(0) if queue else self.default
        if isinstance(item, Exception):
            raise item
        message = SimpleNamespace(content=item, reasoning_content=self.reasoning)
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=20, completion_tokens_details=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)
