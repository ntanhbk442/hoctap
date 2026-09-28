"""Story 2.2: `builder.tts_client` engine selection and `FakeTtsEngine`.

No test here ever calls a real engine's `synthesize()` — only construction/selection is
checked, exactly like `claude_client_test`-style coverage of `ClaudeCliClient` never running
the CLI. `FakeTtsEngine` drives every other test in this story.
"""

from __future__ import annotations

import pytest

from hoctap.builder.tts_client import (
    EDGE_ENGINE,
    GOOGLE_ENGINE,
    EdgeTtsEngine,
    FakeTtsEngine,
    GoogleTtsEngine,
    TtsError,
    estimate_cost_usd,
    fake_mp3_bytes,
    make_engine,
)


def test_edge_tts_package_actually_installs_and_imports() -> None:
    """A bare import only (no network, no API key): proves the real dependency added to
    pyproject.toml via `uv add` actually installs and imports on this Python version, since
    `EdgeTtsEngine.synthesize()` (which does the real `import edge_tts`) is never called by
    any test."""
    import edge_tts

    assert hasattr(edge_tts, "Communicate")


def test_google_cloud_texttospeech_package_actually_installs_and_imports() -> None:
    """Same as above, for the cloud engine's real dependency."""
    import google.cloud.texttospeech as texttospeech

    assert hasattr(texttospeech, "TextToSpeechClient")


def test_make_engine_selects_edge_tts() -> None:
    assert isinstance(make_engine(EDGE_ENGINE), EdgeTtsEngine)


def test_make_engine_selects_google_tts() -> None:
    # Constructing GoogleTtsEngine never touches the network or reads credentials: the
    # client is built lazily on the first `synthesize()` call, which this test never makes.
    assert isinstance(make_engine(GOOGLE_ENGINE), GoogleTtsEngine)


def test_make_engine_rejects_unknown_name() -> None:
    with pytest.raises(TtsError):
        make_engine("not-a-real-engine")


def test_estimate_cost_usd_edge_tts_is_free() -> None:
    assert estimate_cost_usd(EDGE_ENGINE, "xin chào các con") == 0.0


def test_estimate_cost_usd_google_tts_is_positive_for_nonempty_text() -> None:
    assert estimate_cost_usd(GOOGLE_ENGINE, "xin chào") > 0.0
    assert estimate_cost_usd(GOOGLE_ENGINE, "") == 0.0


def test_fake_tts_engine_records_calls_and_returns_deterministic_bytes() -> None:
    fake = FakeTtsEngine()
    a = fake.synthesize("3 < 5", "vi-VN-HoaiMyNeural")
    b = fake.synthesize("3 < 5", "vi-VN-HoaiMyNeural")
    c = fake.synthesize("khác", "vi-VN-HoaiMyNeural")
    assert a == b  # deterministic for the same (text, voice_id)
    assert a != c
    assert fake.calls == [
        ("3 < 5", "vi-VN-HoaiMyNeural"),
        ("3 < 5", "vi-VN-HoaiMyNeural"),
        ("khác", "vi-VN-HoaiMyNeural"),
    ]
    assert a == fake_mp3_bytes("3 < 5", "vi-VN-HoaiMyNeural")


def test_fake_tts_engine_custom_responder_can_raise_tts_error() -> None:
    def flaky(text: str, voice_id: str) -> bytes:
        if text == "boom":
            raise TtsError("gọi thất bại / call failed")
        return b"ok"

    fake = FakeTtsEngine(responder=flaky)
    assert fake.synthesize("fine", "v") == b"ok"
    with pytest.raises(TtsError):
        fake.synthesize("boom", "v")
