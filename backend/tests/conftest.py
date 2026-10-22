import pytest

from clawback import llm
from clawback.tools import tavily

from fakes import FakeLLM


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Tests never reach Token Factory or Tavily, even when backend/.env has real keys."""
    monkeypatch.setattr(llm, "available", lambda: False)
    monkeypatch.setattr(tavily, "available", lambda: False)


@pytest.fixture()
def fake_llm(monkeypatch) -> FakeLLM:
    fake = FakeLLM()
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "_client", lambda: fake)
    return fake
