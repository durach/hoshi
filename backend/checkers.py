"""Load the named checker list, or synthesize one from the env settings.

Validation is deliberately fatal: this runs during startup, where a bad config
should kill the container, not surface later as a 500 with a stack trace.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from providers import GrammarProvider, create_provider


# Names become CSS hooks and API parameters, same as `agent` — same alphabet.
NAME_RE = re.compile(r"^[a-z0-9-]{1,32}$")


@dataclass(frozen=True)
class CheckerConfig:
    name: str
    provider: str
    model: str
    default: bool = False
    base_url: str = ""


@dataclass
class Checkers:
    providers: dict[str, GrammarProvider]
    configs: dict[str, CheckerConfig]
    default: str


def _parse(path: Path) -> list[CheckerConfig]:
    try:
        data: Any = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"checkers.json is not valid JSON: {e}") from e
    entries = data.get("checkers") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ValueError("checkers.json must define at least one entry under 'checkers'")

    configs: list[CheckerConfig] = []
    for entry in entries:
        name = str(entry.get("name", ""))
        if not NAME_RE.match(name):
            raise ValueError(f"checker name {name!r} is not a slug (^[a-z0-9-]{{1,32}}$)")
        if not entry.get("model"):
            raise ValueError(f"checker {name!r} has no model")
        configs.append(
            CheckerConfig(
                name=name,
                provider=str(entry.get("provider", "")),
                model=str(entry["model"]),
                default=bool(entry.get("default", False)),
                base_url=str(entry.get("base_url", "")),
            )
        )

    names = [c.name for c in configs]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        raise ValueError(f"duplicate checker names: {sorted(dupes)}")
    defaults = [c.name for c in configs if c.default]
    if len(defaults) != 1:
        raise ValueError(
            f"exactly one checker must have default: true, found {len(defaults)}"
        )
    return configs


def load_checkers(
    path: str,
    *,
    fallback_provider: str,
    fallback_model: str,
    anthropic_api_key: str = "",
    openai_api_key: str = "",
    gemini_api_key: str = "",
    factory: Callable[..., GrammarProvider] = create_provider,
) -> Checkers:
    file = Path(path)
    if file.is_file():
        configs = _parse(file)
    else:
        # Absent — or a directory, which docker compose creates when the host
        # file does not exist. Either way: the pre-checkers.json behaviour.
        configs = [
            CheckerConfig(
                name="default",
                provider=fallback_provider,
                model=fallback_model,
                default=True,
            )
        ]

    providers = {
        c.name: factory(
            c.provider,
            c.model,
            anthropic_api_key=anthropic_api_key,
            openai_api_key=openai_api_key,
            gemini_api_key=gemini_api_key,
            base_url=c.base_url,
        )
        for c in configs
    }
    return Checkers(
        providers=providers,
        configs={c.name: c for c in configs},
        default=next(c.name for c in configs if c.default),
    )
