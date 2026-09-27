"""Compares the extracted Answer Keys with the second answer, the code and the Hints.

For each Problem the verdict is:

- `disagree`: code arithmetic (`builder.arith`) computed a value that differs from the
  extracted one (`arith`, whatever the model said), or the second answer differs on a
  Part that code could not compute (`answer`);
- `unverified`: no disagreement, but some Part could not be checked: the call failed, the
  Problem or a Part is missing from the output, the output is malformed or inconsistent
  (duplicate or unknown entries or keys), or the model was `unsure`;
- `agree`: otherwise. When code computed the extracted answer exactly and only the model
  differs, exact arithmetic wins: `agree`, with an informational `code_confirms` reason.

A Hint that gives away an answer is a `hint_leak` reason: it does not change the verdict,
but it sets `needs_review`. Checked: every numeric or count slot value (by numeric value;
`,`/`.` decimals and U+2212 accepted; a number preceded by a minus is another number),
the words for a compare row's symbol ("bé hơn", "lớn hơn", "bằng"), and the text of a
selected multiple-choice option.

Comparison, after normalisation (NFC, numbers by value):
keyed answers are compared as `answer_map` maps; `selected` as sets; spot-difference
`regions` by count and a one-to-one matching with IoU >= 0.5; `order` and `sequence` as
lists; `match` as sets of pairs; `fallback` always agrees.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from typing import Any

from pydantic import BaseModel, ValidationError

from hoctap.builder.arith import evaluate, format_number
from hoctap.builder.verify.models import VerifyProblem
from hoctap.content.schema import (
    KEYED_ANSWER_TYPES,
    ComparePart,
    CountEntry,
    MultipleChoicePart,
    NumberInputPart,
    NumericEntry,
    ProblemDoc,
    SpotDifferencePart,
    answer_map,
    parse_number,
)

AGREE, DISAGREE, UNVERIFIED = "agree", "disagree", "unverified"
IOU_MIN = 0.5

# Reason kinds, and the verdict each one forces (hint_leak and code_confirms force none).
ANSWER = "answer"  # the second answer differs
ARITH = "arith"  # code arithmetic differs from the extracted answer
CODE_CONFIRMS = "code_confirms"  # code equals the extracted answer; only the model differs
HINT_LEAK = "hint_leak"
MISSING_PROBLEM = "missing_problem"
MISSING_PART = "missing_part"
TYPE_MISMATCH = "type_mismatch"
INVALID_OUTPUT = "invalid_output"
UNSURE = "unsure"
CALL_FAILED = "call_failed"
NOT_RUN = "not_run"  # no verify result for the current input (yet)
INVALID_DOC = "invalid_doc"  # the stored ProblemDoc no longer validates
_DISAGREE_KINDS = {ANSWER, ARITH}
_UNVERIFIED_KINDS = {
    MISSING_PROBLEM,
    MISSING_PART,
    TYPE_MISMATCH,
    INVALID_OUTPUT,
    UNSURE,
    CALL_FAILED,
    NOT_RUN,
    INVALID_DOC,
}


@dataclass(frozen=True)
class Reason:
    part_key: str | None
    kind: str
    extracted: Any = None
    second: Any = None
    code: Any = None
    slot_key: str | None = None


@dataclass
class Verdict:
    status: str
    reasons: list[Reason] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return self.status != AGREE or any(r.kind == HINT_LEAK for r in self.reasons)

    def reasons_json(self) -> list[dict[str, Any]]:
        return [asdict(r) for r in self.reasons]


def status_of(reasons: list[Reason]) -> str:
    kinds = {r.kind for r in reasons}
    if kinds & _DISAGREE_KINDS:
        return DISAGREE
    if kinds & _UNVERIFIED_KINDS:
        return UNVERIFIED
    return AGREE


# --------------------------------------------------------------------------- normalise


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip()


def _number(value: str) -> Fraction | None:
    number = parse_number(_nfc(value))
    return None if number is None else Fraction(number)


def _norm(value: str) -> Fraction | str:
    number = _number(value)
    return _nfc(value) if number is None else number


def _dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_dump(v) for v in value]
    return value


# --------------------------------------------------------------------------- code arithmetic

_EXPR_EQ_SLOT = re.compile(r"^\s*(?P<expr>[^\[\]=]+?)\s*=\s*\[\[(?P<slot>[^\[\]]+)\]\]\s*$")
_SLOT_EQ_EXPR = re.compile(r"^\s*\[\[(?P<slot>[^\[\]]+)\]\]\s*=\s*(?P<expr>[^\[\]=]+?)\s*$")
_DIVISION = re.compile(r"[:/÷]")


def _code_value(expr: str) -> Fraction | None:
    """The value of an expression for the code check, or None to skip it: a division
    whose result is not a whole number (`7 : 2`, `10 : 3`) may mean a quotient with a
    remainder, so it is left to the model."""
    value = evaluate(expr)
    if value is None or (value.denominator != 1 and _DIVISION.search(expr)):
        return None
    return value


def code_answers(part: Any) -> dict[str, str]:
    """The answers code arithmetic can compute for a Part, `{key: value}`.

    number_input `<expr> = [[slot]]` or `[[slot]] = <expr>`: the slot's value; compare rows
    whose two sides both evaluate: `<`, `>` or `=`. Anything else is skipped.
    """
    if isinstance(part, NumberInputPart):
        text = unicodedata.normalize("NFC", part.template)
        match = _EXPR_EQ_SLOT.fullmatch(text) or _SLOT_EQ_EXPR.fullmatch(text)
        if match is None:
            return {}
        value = _code_value(match.group("expr"))
        return {} if value is None else {match.group("slot"): format_number(value)}
    if isinstance(part, ComparePart):
        out = {}
        for row in part.rows:
            left, right = _code_value(row.left), _code_value(row.right)
            if left is not None and right is not None:
                out[row.slot_key] = "<" if left < right else ">" if left > right else "="
        return out
    return {}


def _same(a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return a is b
    return _norm(a) == _norm(b)


# --------------------------------------------------------------------------- regions


def iou(a: list[float], b: list[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def regions_match(first: list[list[float]], second: list[list[float]]) -> bool:
    """Same count, and a one-to-one matching in which every pair has IoU >= 0.5."""
    if len(first) != len(second):
        return False
    edges = [[j for j, b in enumerate(second) if iou(a, b) >= IOU_MIN] for a in first]
    owner: dict[int, int] = {}

    def augment(i: int, seen: set[int]) -> bool:
        for j in edges[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in owner or augment(owner[j], seen):
                owner[j] = i
                return True
        return False

    return all(augment(i, set()) for i in range(len(first)))


# --------------------------------------------------------------------------- per Part


def _keyed_reasons(part: Any, second: Any) -> list[Reason]:
    extracted = answer_map(part)
    theirs = {e.key: e.value for e in second.answer}
    code = code_answers(part)
    reasons = []
    for key in sorted(set(extracted) | set(theirs) | set(code)):
        mine, other, computed = extracted.get(key), theirs.get(key), code.get(key)
        if computed is not None and not _same(computed, mine):
            kind = ARITH
        elif not _same(mine, other):
            kind = ANSWER if computed is None else CODE_CONFIRMS
        else:
            continue
        reasons.append(Reason(part.part_key, kind, mine, other, computed, key))
    return reasons


def _other_agrees(part: Any, second: Any) -> bool:
    kind = part.type
    if kind == "fallback":
        return True
    mine, theirs = part.answer, second.answer
    if kind in ("multiple_choice", "image_select"):
        return set(mine.selected) == set(theirs.selected)
    if kind == "order":
        return list(mine.order) == list(theirs.order)
    if kind == "connect_dots":
        return list(mine.sequence) == list(theirs.sequence)
    if kind == "match":
        return {tuple(p) for p in mine.pairs} == {tuple(p) for p in theirs.pairs}
    if isinstance(part, SpotDifferencePart):
        return regions_match([r.bbox for r in mine.regions], [r.bbox for r in theirs.regions])
    raise TypeError(f"no comparison for Part type {kind!r}")


def _code_only_reasons(part: Any) -> list[Reason]:
    """Code arithmetic alone (no usable second answer for this Part)."""
    if not isinstance(part, KEYED_ANSWER_TYPES):
        return []
    extracted = answer_map(part)
    return [
        Reason(part.part_key, ARITH, extracted.get(key), None, value, key)
        for key, value in sorted(code_answers(part).items())
        if not _same(value, extracted.get(key))
    ]


def _duplicates(values: list[Any]) -> list[Any]:
    return sorted(str(v) for v, n in Counter(values).items() if n > 1)


def _answer_duplicates(second: Any) -> list[str]:
    """Keys that occur more than once inside a second answer."""
    answer = second.answer
    if isinstance(answer, list):  # keyed entries
        return _duplicates([e.key for e in answer])
    if hasattr(answer, "selected"):
        return _duplicates(answer.selected)
    if hasattr(answer, "order"):
        return _duplicates(answer.order)
    if hasattr(answer, "pairs"):
        return _duplicates([p[0] for p in answer.pairs])
    if hasattr(answer, "regions"):
        return _duplicates([r.region_key for r in answer.regions])
    return []


# --------------------------------------------------------------------------- hint leaks

# A number token: not part of a longer number; a leading minus (ASCII or U+2212) that is
# not preceded by a digit belongs to the token (so "-3" is not "3").
_NUMBER_TOKEN = re.compile(
    r"(?<![\d.,])(?P<sign>(?<!\d)[-−](?=\d))?(?P<num>\d+(?:[.,]\d+)?)(?![.,]?\d)"
)
_SYMBOL_WORDS = {"<": ("bé hơn", "nhỏ hơn"), ">": ("lớn hơn",), "=": ("bằng",)}


def hint_numbers(hint: str) -> set[Fraction]:
    """Every standalone number in a Hint, by value."""
    text = unicodedata.normalize("NFC", hint)
    found = set()
    for match in _NUMBER_TOKEN.finditer(text):
        value = Fraction(match.group("num").replace(",", "."))
        found.add(-value if match.group("sign") else value)
    return found


def _has_words(text: str, words: str) -> bool:
    pattern = r"(?<!\w)" + re.escape(words.casefold()) + r"(?!\w)"
    return re.search(pattern, unicodedata.normalize("NFC", text).casefold()) is not None


def hint_leaks(part: Any) -> list[Reason]:
    """`hint_leak` reasons for every answer value the Part's Hint gives away."""
    hint = unicodedata.normalize("NFC", part.hint)
    reasons = []
    if isinstance(part, ComparePart):
        for entry in part.answer:
            if any(_has_words(hint, w) for w in _SYMBOL_WORDS[entry.value]):
                reasons.append(Reason(part.part_key, HINT_LEAK, entry.value, hint, None, entry.key))
    elif isinstance(part, KEYED_ANSWER_TYPES):
        numbers = hint_numbers(hint)
        for entry in part.answer:
            if isinstance(entry, NumericEntry | CountEntry):
                value = _number(entry.value)
                if value is not None and value in numbers:
                    reasons.append(
                        Reason(part.part_key, HINT_LEAK, entry.value, hint, None, entry.key)
                    )
    elif isinstance(part, MultipleChoicePart):
        options = {o.option_key: o.text for o in part.options}
        numbers = hint_numbers(hint)
        for key in part.answer.selected:
            text = options.get(key)
            if not text or not text.strip():
                continue
            value = _number(text)
            leaked = value in numbers if value is not None else _has_words(hint, _nfc(text))
            if leaked:
                reasons.append(Reason(part.part_key, HINT_LEAK, text, hint, None, key))
    return reasons


# --------------------------------------------------------------------------- per Problem


def _part_reasons(part: Any, other: Any) -> list[Reason]:
    """The comparison reasons of one Part against its (single, well-formed) second answer."""
    if other.type != part.type:
        return [Reason(part.part_key, TYPE_MISMATCH, part.type, other.type)]
    duplicates = _answer_duplicates(other)
    if duplicates:
        return [Reason(part.part_key, INVALID_OUTPUT, second=f"duplicate keys: {duplicates}")]
    if other.unsure:
        return [Reason(part.part_key, UNSURE, _dump(part.answer), _dump(other.answer))]
    if isinstance(part, KEYED_ANSWER_TYPES):
        return _keyed_reasons(part, other)
    if not _other_agrees(part, other):
        return [Reason(part.part_key, ANSWER, _dump(part.answer), _dump(other.answer))]
    return []


def verdict_for(
    doc: ProblemDoc, second: Any, failure: str | None = None, invalid: str | None = None
) -> Verdict:
    """The verdict of one Problem.

    `second` is the raw output entry for this Problem (None when it is missing), and
    `failure` the reason the page's call failed (then `second` is ignored). `invalid`
    says why the page's output is inconsistent for this Problem (a duplicate or unknown
    problem_id): the Problem is at best `unverified`.
    """
    reasons: list[Reason] = []
    parsed: VerifyProblem | None = None
    if failure is not None:
        reasons.append(Reason(None, CALL_FAILED, second=failure))
    elif second is None:
        reasons.append(Reason(None, MISSING_PROBLEM))
    else:
        if invalid is not None:
            reasons.append(Reason(None, INVALID_OUTPUT, second=invalid))
        try:
            parsed = VerifyProblem.model_validate(second)
        except ValidationError as exc:
            message = exc.errors(include_url=False)[0].get("msg", "invalid")
            reasons.append(Reason(None, INVALID_OUTPUT, second=f"{exc.error_count()}: {message}"))

    by_key: dict[str, list[Any]] = {}
    for item in parsed.parts if parsed is not None else []:
        by_key.setdefault(item.part_key, []).append(item)
    if parsed is not None:
        known = {p.part_key for p in doc.parts}
        unknown = sorted(set(by_key) - known)
        if unknown:
            reasons.append(Reason(None, INVALID_OUTPUT, second=f"unknown part_keys: {unknown}"))

    for part in doc.parts:
        others = by_key.get(part.part_key, [])
        if parsed is None:
            reasons += _code_only_reasons(part)
        elif not others:
            reasons.append(Reason(part.part_key, MISSING_PART))
            reasons += _code_only_reasons(part)
        elif len(others) > 1:
            reasons.append(Reason(part.part_key, INVALID_OUTPUT, second="duplicate part_key"))
            reasons += _code_only_reasons(part)
        else:
            part_reasons = _part_reasons(part, others[0])
            if any(r.kind in _UNVERIFIED_KINDS for r in part_reasons):
                part_reasons += _code_only_reasons(part)
            reasons += part_reasons
        reasons += hint_leaks(part)
    return Verdict(status_of(reasons), reasons)
