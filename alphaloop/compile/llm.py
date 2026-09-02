"""Provider-agnostic LLM compiler: idea -> StrategySpec YAML.

Provider is chosen by the ``ALPHALOOP_LLM_PROVIDER`` env var
(``anthropic`` | ``openai`` | ``xai`` | ``ollama``), each reading its own
API key/host from env. This module never runs a spec — it only produces
one, which the CLI always shows for confirm/edit before ``alphaloop run``
touches it (see ``alphaloop.core.confirm``).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from alphaloop.core.spec import StrategySpec

_PROMPTS_DIR = Path(__file__).parent / "prompts"


class LLMProvider(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class AnthropicProvider:
    def __init__(self, model: str = "claude-sonnet-5", api_key: str | None = None) -> None:
        self.model = model
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def complete(self, system: str, user: str) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)
        resp = client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in resp.content if block.type == "text")


class OpenAIProvider:
    def __init__(
        self, model: str = "gpt-4o", api_key: str | None = None, base_url: str | None = None
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ["OPENAI_API_KEY"]
        self.base_url = base_url

    def complete(self, system: str, user: str) -> str:
        import openai

        client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
        resp = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return resp.choices[0].message.content or ""


class XAIProvider(OpenAIProvider):
    """xAI's Grok chat API is OpenAI-compatible."""

    def __init__(self, model: str = "grok-4", api_key: str | None = None) -> None:
        super().__init__(
            model=model,
            api_key=api_key or os.environ["ALPHALOOP_XAI_API_KEY"],
            base_url="https://api.x.ai/v1",
        )


class OllamaProvider:
    def __init__(self, model: str = "llama3.1", host: str | None = None) -> None:
        self.model = model
        self.host = host or os.environ.get("ALPHALOOP_OLLAMA_HOST", "http://localhost:11434")

    def complete(self, system: str, user: str) -> str:
        import requests

        resp = requests.post(
            f"{self.host}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return str(resp.json()["message"]["content"])


_PROVIDERS: dict[str, type[LLMProvider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "xai": XAIProvider,
    "ollama": OllamaProvider,
}


def get_provider(name: str | None = None) -> LLMProvider:
    name = name or os.environ.get("ALPHALOOP_LLM_PROVIDER", "anthropic")
    if name not in _PROVIDERS:
        raise ValueError(f"unknown LLM provider {name!r}; expected one of {sorted(_PROVIDERS)}")
    return _PROVIDERS[name]()


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:] if lines else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


class StrategyCompiler:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider or get_provider()

    def compile(self, idea: str, killed_hypotheses: list[str] | None = None) -> StrategySpec:
        system = (_PROMPTS_DIR / "compile_spec.md").read_text()
        killed_block = ""
        if killed_hypotheses:
            killed_block = (
                "PAST KILLED HYPOTHESES (avoid re-proposing unchanged):\n"
                + "\n".join(f"- {h}" for h in killed_hypotheses)
                + "\n\n"
            )
        response = self.provider.complete(system, killed_block + f"IDEA:\n{idea}")
        yaml_text = _strip_code_fence(response)
        return StrategySpec.from_yaml(yaml_text)

    def propose_next_experiments(
        self,
        spec: StrategySpec,
        verdict: str,
        grade: str,
        scorecard_markdown: str,
        killed_hypotheses: list[str] | None = None,
    ) -> str:
        system = (_PROMPTS_DIR / "next_experiments.md").read_text()
        killed_block = ""
        if killed_hypotheses:
            killed_block = (
                "PAST KILLED HYPOTHESES:\n"
                + "\n".join(f"- {h}" for h in killed_hypotheses)
                + "\n\n"
            )
        user = (
            f"{killed_block}SPEC:\n{spec.to_yaml()}\nVERDICT: {verdict}\nGRADE: {grade}\n\n"
            f"SCORECARD:\n{scorecard_markdown}"
        )
        return self.provider.complete(system, user)
