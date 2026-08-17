import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class GrammarResult:
    has_issues: bool
    explanation: str
    types: list[str] = field(default_factory=list)
    issues: list[dict[str, str]] = field(default_factory=list)
    correction: str = ""
    # Kept for the debug panel, never for display: the response exactly as the
    # provider returned it, and whatever normalisation removed from it.
    raw: dict[str, Any] = field(default_factory=dict)
    dropped_issues: list[dict[str, str]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)


# The categories a finding can carry. Providers enforce this list as a schema
# enum rather than trusting the prompt, so an off-vocabulary label is impossible
# instead of merely discouraged.
ISSUE_TYPES = ["grammar", "spelling", "punctuation", "word-choice", "style"]

# The model reports findings; it is not asked for summary flags. has_issues and
# the header types are derived from this list server-side, so the model cannot
# contradict itself by, say, claiming issues while listing none.
GRAMMAR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ISSUE_TYPES},
                    "note": {"type": "string"},
                },
                "required": ["type", "note"],
                "additionalProperties": False,
            },
        },
        "correction": {"type": "string"},
    },
    "required": ["issues", "correction"],
    "additionalProperties": False,
}


def build_result(data: dict[str, Any]) -> GrammarResult:
    """Turn a provider's schema-shaped response into a GrammarResult.

    Shared by all three providers: they differ in how they obtain the dict, not
    in what it means. A style note is a remark, not a fault, so it never sets
    has_issues on its own.
    """
    reported = data.get("issues", [])
    issues = [
        {"type": str(i["type"]), "note": str(i.get("note", ""))}
        for i in reported
        if i.get("type") in ISSUE_TYPES
    ]
    dropped = [
        {"type": str(i.get("type", "")), "note": str(i.get("note", ""))}
        for i in reported
        if i.get("type") not in ISSUE_TYPES
    ]
    types = list(dict.fromkeys(i["type"] for i in issues))
    return GrammarResult(
        has_issues=any(i["type"] != "style" for i in issues),
        explanation="",
        types=types,
        issues=issues,
        correction=str(data.get("correction", "")),
        raw=data,
        dropped_issues=dropped,
    )


SYSTEM_PROMPT = (
    "You check the grammar of prompts typed into a coding assistant. They are "
    "short, informal and often fragments rather than full sentences — judge them "
    "as speech, not as written prose.\n\n"
    "Return one entry in `issues` per distinct mistake, each with its type and a "
    "one-sentence note naming what is wrong. Report only genuine mistakes: "
    "subject-verb agreement, verb tense and form, plural and countable/uncountable "
    "nouns, articles, pronoun case, word order, preposition choice, and "
    "apostrophes that change the word (its/it's, lets/let's, your/you're).\n\n"
    "Never treat any of these as a mistake:\n"
    "- a missing period or other punctuation at the end\n"
    "- a lowercase letter starting the text\n"
    "- missing commas that do not change the meaning\n"
    "- spelling of technical terms, product names, file paths, code or URLs\n\n"
    "Informal, colloquial or slangy wording is not a mistake either — it is normal "
    "here. You may add at most one issue of type 'style', and only when it is "
    "genuinely worth knowing, never a rewrite that is merely more polished.\n\n"
    "Choose each type from: "
    + ", ".join(ISSUE_TYPES)
    + ". Name the actual mistake in the note — never describe it as a "
    "capitalization or punctuation problem when it is really something else. "
    "Return an empty `issues` list when the text is fine.\n\n"
    "Put the whole corrected text in `correction`, once, keeping the original's "
    "capitalization and ending punctuation: do not capitalize the first word or "
    "add a final period that was not there. Leave `correction` empty when there is "
    "nothing to correct, including when your only issue is a style note.\n\n"
    "In `correction`, wrap every part you changed in <mark> tags, and give each "
    "one a data-type attribute naming the issue it fixes, using the same type you "
    'gave that issue. For example: he <mark data-type="grammar">goes</mark> to '
    'the store, or I <mark data-type="spelling">received</mark> it. Always mark '
    "whole words: if only part of a "
    "word changes, put the entire corrected word inside the tag (cant becomes "
    "<mark data-type=\"grammar\">can't</mark>), never just the changed letters. "
    "Every marked word must "
    "actually differ from the original — never mark a word you left unchanged, and "
    "never leave a word you corrected unmarked. Write it as plain text, never "
    "inside backticks or a code block, or the marks will show up as literal "
    "characters instead of a highlight.\n\n"
    "If the text runs to several paragraphs, keep them all in `correction` and "
    "preserve the line breaks; never return only the paragraph you happened to "
    "change.\n\n"
    "Notes and correction are markdown."
)

# Stored with every result so two results can be told apart by the prompt that
# produced them. The text itself is 2.3 KB and identical across a run, so it is
# served once from its own endpoint rather than copied 1000 times.
SYSTEM_PROMPT_HASH = hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()[:8]


def parse_provider_json(text: str) -> dict[str, Any]:
    """Strip markdown fences and parse JSON from LLM response."""
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    try:
        result: dict[str, Any] = json.loads(cleaned)
        return result
    except json.JSONDecodeError as e:
        raise ValueError(f"Provider returned invalid JSON: {e}") from e


class GrammarProvider(Protocol):
    async def check_grammar(self, text: str) -> GrammarResult: ...


def create_provider(
    provider: str,
    model: str,
    *,
    anthropic_api_key: str = "",
    openai_api_key: str = "",
    gemini_api_key: str = "",
    base_url: str = "",
    reasoning_effort: str = "",
) -> GrammarProvider:
    if base_url and provider != "openai":
        raise ValueError(f"base_url is only supported for the openai provider, not {provider!r}")
    if reasoning_effort and provider != "openai":
        raise ValueError(
            f"reasoning_effort is only supported for the openai provider, not {provider!r}"
        )
    match provider:
        case "anthropic":
            from providers.anthropic import AnthropicProvider

            return AnthropicProvider(api_key=anthropic_api_key, model=model)
        case "openai":
            from providers.openai import OpenAIProvider

            return OpenAIProvider(
                api_key=openai_api_key,
                model=model,
                base_url=base_url,
                reasoning_effort=reasoning_effort,
            )
        case "gemini":
            from providers.gemini import GeminiProvider

            return GeminiProvider(api_key=gemini_api_key, model=model)
        case _:
            raise ValueError(f"Unknown provider: {provider}")
