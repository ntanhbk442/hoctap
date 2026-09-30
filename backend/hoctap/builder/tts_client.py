"""All TTS access goes through `TtsEngine`: `synthesize(text, voice_id) -> bytes` (raw mp3).

Two real engines, selected by `Settings.tts_engine`:

- `EdgeTtsEngine` (`"edge-tts"`, the default): Microsoft's free, no-API-key online voices,
  via the `edge-tts` package. No account, no spend.
- `GoogleTtsEngine` (`"google-tts"`): Google Cloud Text-to-Speech, via
  `google-cloud-texttospeech`. Chosen over Azure Cognitive Services Speech for this story
  because its Python client is a plain gRPC/REST wrapper (no native SDK binary to install,
  smaller dependency footprint) and it has a documented Vietnamese neural voice. Credentials
  come from the environment only (`GOOGLE_APPLICATION_CREDENTIALS`), per `config.py`'s
  secrets rule; never stored in `hoctap.toml` or the database.

Both are real, working clients — but exactly like `ClaudeCliClient`, no automated test ever
calls a real engine. `FakeTtsEngine` drives every test, mirroring `FakeClaudeClient`: a
`responder(text, voice_id)` builds each call's bytes (or raises `TtsError`), and every call
is recorded.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

EDGE_ENGINE = "edge-tts"
GOOGLE_ENGINE = "google-tts"
ENGINE_NAMES: tuple[str, ...] = (EDGE_ENGINE, GOOGLE_ENGINE)

# USD per character, for the pre-flight/spend-cap estimate (`tts_max_total_usd`). edge-tts
# is free; the Google figure is Google Cloud TTS's standard (non-WaveNet/Neural2) voice
# price as published at the time of writing (~$4 per 1,000,000 characters) — a rough
# estimate, not billing-accurate; the real cost is whatever Google invoices separately.
PRICE_PER_CHAR_USD: dict[str, float] = {
    EDGE_ENGINE: 0.0,
    GOOGLE_ENGINE: 4.0 / 1_000_000,
}


class TtsError(Exception):
    """A TTS call failed (bilingual message); the caller records it and moves on."""


class TtsEngine:
    """The adapter interface every engine (real or fake) implements."""

    def synthesize(self, text: str, voice_id: str) -> bytes:  # pragma: no cover - interface
        raise NotImplementedError


def estimate_cost_usd(engine_name: str, text: str) -> float:
    """The pre-flight cost estimate of one call, in USD (0.0 for an unknown engine name)."""
    return PRICE_PER_CHAR_USD.get(engine_name, 0.0) * len(text)


class GoogleTtsEngine(TtsEngine):
    """Real client: Google Cloud Text-to-Speech. The API client is built lazily (on the
    first `synthesize()` call), so constructing this class never touches the network or
    reads credentials — only calling it does."""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):  # noqa: ANN202 - the google-cloud-texttospeech client type
        if self._client is None:
            from google.cloud import texttospeech

            self._client = texttospeech.TextToSpeechClient()
        return self._client

    def synthesize(self, text: str, voice_id: str) -> bytes:
        from google.api_core.exceptions import GoogleAPICallError, RetryError
        from google.auth.exceptions import GoogleAuthError
        from google.cloud import texttospeech

        language_code = "-".join(voice_id.split("-")[:2]) or "vi-VN"
        try:
            client = self._get_client()
            response = client.synthesize_speech(
                input=texttospeech.SynthesisInput(text=text),
                voice=texttospeech.VoiceSelectionParams(
                    language_code=language_code, name=voice_id
                ),
                audio_config=texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.MP3
                ),
            )
        except GoogleAPICallError as exc:
            raise TtsError(
                f"Google TTS gọi thất bại / Google TTS call failed: {exc}"
            ) from exc
        except (GoogleAuthError, RetryError, OSError) as exc:
            raise TtsError(
                f"Google TTS: lỗi thông tin xác thực hoặc mạng / "
                f"credentials or network error: {exc}"
            ) from exc
        audio = bytes(response.audio_content)
        if not audio:
            raise TtsError("Google TTS không trả về âm thanh nào / Google TTS returned no audio")
        return audio


class EdgeTtsEngine(TtsEngine):
    """Real client: `edge-tts` (Microsoft Edge's free online voices, no API key)."""

    def synthesize(self, text: str, voice_id: str) -> bytes:
        import edge_tts

        try:
            communicate = edge_tts.Communicate(text, voice_id)
            audio = bytearray()
            for chunk in communicate.stream_sync():
                if chunk.get("type") == "audio":
                    audio += chunk["data"]
        except edge_tts.exceptions.EdgeTTSException as exc:
            raise TtsError(f"edge-tts gọi thất bại / edge-tts call failed: {exc}") from exc
        except OSError as exc:
            raise TtsError(f"edge-tts: lỗi mạng / network error: {exc}") from exc
        if not audio:
            raise TtsError(
                "edge-tts không trả về âm thanh nào / edge-tts returned no audio"
            )
        return bytes(audio)


def make_engine(engine_name: str) -> TtsEngine:
    """The real engine for a config `tts_engine` name. Only ever called by the CLI: no
    automated test constructs a real engine and calls `synthesize()`."""
    if engine_name == EDGE_ENGINE:
        return EdgeTtsEngine()
    if engine_name == GOOGLE_ENGINE:
        return GoogleTtsEngine()
    raise TtsError(f"tts_engine không hợp lệ / unknown tts_engine: {engine_name!r}")


Responder = Callable[[str, str], bytes]


def fake_mp3_bytes(text: str, voice_id: str) -> bytes:
    """Deterministic fake "mp3" bytes for a (text, voice_id) pair: not real audio, just
    distinct, reproducible bytes for tests to assert against."""
    return b"FAKE-MP3:" + hashlib.sha256(f"{text}|{voice_id}".encode()).digest()


@dataclass
class FakeTtsEngine(TtsEngine):
    """An in-memory engine: `responder(text, voice_id)` builds each call's bytes (a
    responder may raise `TtsError` to simulate an engine failure). Thread-safe: calls may
    come from a worker pool. Defaults to `fake_mp3_bytes`."""

    responder: Responder = fake_mp3_bytes
    calls: list[tuple[str, str]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def synthesize(self, text: str, voice_id: str) -> bytes:
        with self._lock:
            self.calls.append((text, voice_id))
        return self.responder(text, voice_id)
