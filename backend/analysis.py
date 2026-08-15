"""What a correction actually changed, independent of any provider.

Pure functions over (original, correction). They report where the model marked a
span it did not in fact change — a strong hint that the finding behind it was
invented rather than merely worded oddly.

Nothing here alters a verdict. Word alignment is a heuristic: on a heavily
rewritten multi-paragraph correction it can align badly and call a real change a
ghost, so these findings are recorded for a human to read, not acted on.
"""

import difflib
import re
from typing import Any, cast


_MARKED = re.compile(r"<mark[^>]*>(.*?)</mark>", re.S)
_SPLIT = re.compile(r"(<mark[^>]*>.*?</mark>)", re.S)
_DATA_TYPE = re.compile(r'data-type="([^"]*)"')
_WORD = re.compile(r"\S+")


def strip_marks(correction: str) -> tuple[str, list[dict[str, Any]]]:
    """The correction without its tags, plus every marked span located in it.

    Offsets index the returned text, so a caller can find a span again without
    parsing the markup a second time.
    """
    out: list[str] = []
    spans: list[dict[str, Any]] = []
    pos = 0
    for part in _SPLIT.split(correction):
        if not part:
            continue
        marked = _MARKED.fullmatch(part)
        if marked:
            body = marked.group(1)
            found = _DATA_TYPE.search(part)
            spans.append(
                {
                    "text": body,
                    "type": found.group(1) if found else "",
                    "offset": pos,
                    "end": pos + len(body),
                }
            )
            out.append(body)
            pos += len(body)
        else:
            out.append(part)
            pos += len(part)
    return "".join(out), spans


def _words(text: str) -> list[str]:
    return [m.group() for m in _WORD.finditer(text)]


def _opcodes(original: str, stripped: str) -> list[tuple[str, int, int, int, int]]:
    matcher = difflib.SequenceMatcher(
        a=_words(original), b=_words(stripped), autojunk=False
    )
    return cast("list[tuple[str, int, int, int, int]]", matcher.get_opcodes())


def ghost_marks(original: str, correction: str) -> list[dict[str, Any]]:
    """Marked spans covering only words that appear unchanged from the original."""
    stripped, spans = strip_marks(correction)
    total = len(_words(stripped))
    changed: set[int] = set()
    for tag, _i1, _i2, j1, j2 in _opcodes(original, stripped):
        if tag in ("replace", "insert"):
            changed.update(range(j1, j2))
        elif tag == "delete":
            # A deletion leaves no changed word to wrap, so the model marks a
            # survivor beside the gap. Count the two words bordering the
            # deletion point as changed, or a real fix reads as a ghost. A
            # deletion at either end of the text has only one neighbour.
            changed.update(i for i in (j1 - 1, j1) if 0 <= i < total)

    positions = [(m.start(), m.end()) for m in _WORD.finditer(stripped)]
    ghosts: list[dict[str, Any]] = []
    for span in spans:
        covered = [
            i
            for i, (start, end) in enumerate(positions)
            if start < span["end"] and end > span["offset"]
        ]
        if covered and not any(i in changed for i in covered):
            ghosts.append(
                {"text": span["text"], "type": span["type"], "offset": span["offset"]}
            )
    return ghosts


def is_no_op(original: str, correction: str) -> bool:
    """True when the correction says exactly what the original already said."""
    stripped, _ = strip_marks(correction)
    return stripped.strip() == original.strip()


def _slice(text: str, positions: list[tuple[int, int]], lo: int, hi: int) -> str:
    """The source text spanning words lo..hi, whitespace and all.

    Sliced rather than re-joined with spaces so a segment covering a line break
    keeps it: the diff is what the dashboard shows, and a multi-paragraph
    correction rendered as one run-on line is unreadable.
    """
    if hi <= lo:
        return ""
    return text[positions[lo][0] : positions[hi - 1][1]]


def word_diff(original: str, correction: str) -> list[dict[str, str]]:
    """The correction against the original, as flat segments for a renderer.

    Each changed segment carries the type of the marked span it falls inside,
    so the dashboard can colour an insertion by the issue it fixes rather than
    painting every change the same green. Deletions carry no type: the model
    marks a survivor beside the gap, never the removed words themselves.

    Emitted server-side so the browser never needs its own diff: the algorithm
    is already here, and a second implementation would be a second thing to keep
    correct.
    """
    stripped, spans = strip_marks(correction)
    src = [(m.start(), m.end()) for m in _WORD.finditer(original)]
    dst = [(m.start(), m.end()) for m in _WORD.finditer(stripped)]

    segments: list[dict[str, str]] = []
    bounds: list[tuple[int, int]] = []
    for tag, i1, i2, j1, j2 in _opcodes(original, stripped):
        if j2 > j1:
            start, end = dst[j1][0], dst[j2 - 1][1]
        else:
            # A deletion occupies no space in the correction; it sits at the
            # seam between the surrounding words.
            start = end = dst[j1 - 1][1] if j1 else 0
        segment = {
            "op": tag,
            "before": _slice(original, src, i1, i2),
            "after": _slice(stripped, dst, j1, j2),
            "type": "",
            "sep": "",
        }
        if tag != "equal" and j2 > j1:
            for span in spans:
                if span["offset"] < end and span["end"] > start:
                    segment["type"] = span["type"]
                    break
        segments.append(segment)
        bounds.append((start, end))

    # The whitespace that actually separated each segment from the next, so a
    # renderer can reassemble the text without inventing single spaces where the
    # original had a line break.
    for index, segment in enumerate(segments[:-1]):
        segment["sep"] = stripped[bounds[index][1] : bounds[index + 1][0]]
    return segments


def analyse(original: str, correction: str) -> dict[str, Any]:
    """Everything the debug panel reports about one correction."""
    if not correction:
        return {"no_op": False, "ghost_marks": [], "diff": []}
    return {
        "no_op": is_no_op(original, correction),
        "ghost_marks": ghost_marks(original, correction),
        "diff": word_diff(original, correction),
    }
