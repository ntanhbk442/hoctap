"""Vietnamese maths read-aloud text, and the content-addressed `speech_key` (AD-8).

`speech_text()` is the single normaliser: it turns the small set of maths notations the
extractor emits (comparison/arithmetic operators, `\\overline{...}`, `\\frac{a}{b}`) into
spoken Vietnamese. It is a v1 normaliser, not a full LaTeX parser — any other backslash
markup, and any plain digit or word outside those notations, passes through unchanged
(NFC-normalised) and the function never raises.

Known v1 limitations (not fixed here — see `deferred-work.md`):
- `\\overline{...}`/`\\frac{...}{...}` only match a braced body of plain ASCII digits and
  letters (`[0-9A-Za-z]*`): no nested `\\overline`/`\\frac`, no operators, no spaces inside
  the braces. This is deliberate, not an oversight — it is what keeps a nested case like
  `\\frac{\\overline{2}}{3}` from being double-processed (the inner `\\overline{2}` is
  substituted to "số hai" first; the outer `\\frac{...}` regex then does *not* match, because
  "số hai" contains a space and a non-ASCII character, so it is left as literal text next to
  the substituted numerator rather than being re-spelled character by character). A case
  like this is left partially normalised (never garbled, never raises), which is the correct
  v1 trade-off, not full nested-notation support.
- The operator substitution (`<`,`>`,`=`,`+`,`-`,`×`,`*`,`÷`,`/`) is a blind, context-free
  `str.replace()` over the whole text, run after the two regexes above. It is deliberately
  *not* restricted to the small `[0-9A-Za-z]*` body of a matched `\\overline`/`\\frac` (a
  matched body never contains an operator character, since operators are outside that
  charclass), but it *is* unrestricted everywhere else: a literal `-` or `=` in ordinary
  Vietnamese prose (not maths), or inside unrecognised markup, is read as "trừ"/"bằng" too.
  Distinguishing "operator between numbers" from "hyphen in prose" needs more than a
  character-level pass (e.g. digit-adjacency detection) and is deferred.

`speech_key()` hashes the normalised spoken text together with the voice id, so editing a
Problem's text (or switching voice) naturally changes its key; the old audio file is simply
orphaned (see `builder.stages.speak`), never deleted here. `speech_url()`/`speech_path()`
mirror `content.assets`'s URL/path helpers, one folder over (`assets/audio/` instead of
`assets/crops/`).

`problem_speech_refs()` is the one place that lists every text an audio button may need for
a Problem: `instruction`, `display_label`, and each Part's `prompt`, `hint` and Solution
`steps`/`final` — never `answer`, which is never read aloud (AD-5: a played clip must not
give away the Answer Key). `guide_speech_refs()` does the same for a Concept Guide (its
explanation and worked example, all of which may be spoken). Each `SpeechRef.text` is the
NORMALISED spoken text (`speech_text()` of the raw field) — this is what must be sent to
the TTS engine; `speech_key` is the hash of that same normalised text plus the voice id, so
the two always agree on what was actually (or would be) spoken.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from hoctap.content.assets import ASSETS_URL
from hoctap.content.schema import ConceptGuideDoc, ProblemDoc

# Vietnamese digit words, used for digit-by-digit reading (overline) and for the numerator/
# denominator of a fraction. A v1 approximation: multi-digit numbers are read digit by
# digit, not as one Vietnamese number word (e.g. "12" -> "một hai", not "mười hai");
# improving this to full number-to-words is deferred (see deferred-work.md).
_DIGIT_WORDS: dict[str, str] = {
    "0": "không",
    "1": "một",
    "2": "hai",
    "3": "ba",
    "4": "bốn",
    "5": "năm",
    "6": "sáu",
    "7": "bảy",
    "8": "tám",
    "9": "chín",
}

# A blind, context-free replacement below (see the module docstring's "known v1
# limitations"): safe against a matched `\overline{...}`/`\frac{...}{...}` body (which can
# never contain one of these characters, see `_OVERLINE_RE`/`_FRAC_RE`), but not safe
# against a literal operator character in ordinary prose.
_OPERATOR_WORDS: tuple[tuple[str, str], ...] = (
    ("<", "bé hơn"),
    (">", "lớn hơn"),
    ("=", "bằng"),
    ("+", "cộng"),
    ("-", "trừ"),
    ("×", "nhân"),
    ("*", "nhân"),
    ("÷", "chia"),
    ("/", "chia"),
)

# The captured body is restricted to plain ASCII digits/letters (never braces, backslashes,
# spaces or operator characters) so that (a) a nested `\overline{...}`/`\frac{...}{...}`
# can never match through to an inner, not-yet-substituted body, and (b) the result of one
# substitution (Vietnamese words, with spaces and diacritics) can never itself be re-matched
# and re-spelled by the other regex — see the module docstring's "known v1 limitations".
_OVERLINE_RE = re.compile(r"\\overline\{([0-9A-Za-z]*)\}")
_FRAC_RE = re.compile(r"\\frac\{([0-9A-Za-z]*)\}\{([0-9A-Za-z]*)\}")


def _spell(chars: str) -> str:
    """Each character read individually: a digit by its Vietnamese word, anything else
    (a letter placeholder) literally."""
    return " ".join(_DIGIT_WORDS.get(ch, ch) for ch in chars)


def _replace_overline(match: re.Match[str]) -> str:
    return f"số {_spell(match.group(1))}"


def _replace_frac(match: re.Match[str]) -> str:
    return f"{_spell(match.group(1))} phần {_spell(match.group(2))}"


def speech_text(text: str) -> str:
    """The Vietnamese read-aloud text for `text`. Never raises: unrecognised backslash
    markup is left as literal text."""
    value = unicodedata.normalize("NFC", text)
    value = _OVERLINE_RE.sub(_replace_overline, value)
    value = _FRAC_RE.sub(_replace_frac, value)
    for char, word in _OPERATOR_WORDS:
        if char in value:
            value = value.replace(char, f" {word} ")
    return unicodedata.normalize("NFC", " ".join(value.split()))


def speech_key(text: str, voice_id: str) -> str:
    """The content-addressed key of `text` read in `voice_id`: changes whenever the
    spoken text or the voice changes."""
    normalized = unicodedata.normalize("NFC", speech_text(text))
    return hashlib.sha256((normalized + voice_id).encode("utf-8")).hexdigest()[:16]


def speech_url(speech_key: str) -> str:
    return f"{ASSETS_URL}/audio/{speech_key}.mp3"


def speech_path(data_dir: Path, speech_key: str) -> Path:
    return data_dir / "assets" / "audio" / f"{speech_key}.mp3"


@dataclass(frozen=True)
class SpeechRef:
    """`text` is the NORMALISED spoken text (`speech_text()` of the raw field) — this, not
    the raw field, is what must be sent to a `TtsEngine`. `speech_key` is the hash of that
    same normalised text plus the voice id (see `speech_key()`)."""

    text: str
    speech_key: str


def problem_speech_refs(doc: ProblemDoc, voice_id: str) -> list[SpeechRef]:
    """Every (normalised text, speech_key) an audio button may need for this Problem,
    deduplicated by key, in a stable order (`instruction`, `display_label`, then per Part in
    document order: `prompt`, `hint`, Solution `steps`, `final`). Never `answer`. `doc.parts`
    may be empty for a duck-typed stub in a test (a real `ProblemDoc` always has at least
    one); only `instruction`/`display_label` are returned in that case."""
    texts: list[str] = [doc.instruction, doc.display_label]
    for part in doc.parts:
        texts.append(part.prompt)
        texts.append(part.hint)
        texts.extend(part.solution.steps)
        texts.append(part.solution.final)
    seen: dict[str, SpeechRef] = {}
    for raw in texts:
        if not raw:
            continue
        key = speech_key(raw, voice_id)
        if key in seen:
            continue
        seen[key] = SpeechRef(speech_text(raw), key)
    return list(seen.values())


def guide_speech_refs(doc: ConceptGuideDoc, voice_id: str) -> list[SpeechRef]:
    """Every (normalised text, speech_key) of a Concept Guide: `explanation`, then the
    example's `question`, `steps` and `answer`; deduplicated by key, in that order."""
    texts = [doc.explanation, doc.example.question, *doc.example.steps, doc.example.answer]
    seen: dict[str, SpeechRef] = {}
    for raw in texts:
        if not raw:
            continue
        key = speech_key(raw, voice_id)
        if key not in seen:
            seen[key] = SpeechRef(speech_text(raw), key)
    return list(seen.values())
