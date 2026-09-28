"""Settings loaded from `hoctap.toml` plus `HOCTAP_*` environment variables.

Precedence (highest first): environment variables, `hoctap.toml`, defaults.
The config file is `$HOCTAP_CONFIG` if set, otherwise `<repo root>/hoctap.toml`.
Relative paths in the file are resolved against the file's folder; relative paths
from the environment or defaults are resolved against the repo root.
Secrets (ANTHROPIC_API_KEY, TTS keys) are read from the environment by the
modules that need them and are never stored here or in the database.
"""

from __future__ import annotations

import math
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_PATH_KEYS = ("data_dir", "frontend_dist", "source_dir", "tls_cert_dir")
_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
# Kept in sync with `builder.tts_client.ENGINE_NAMES` (not imported, to keep config.py
# free of the builder's dependencies).
_TTS_ENGINES = {"edge-tts", "google-tts"}


class ConfigError(ValueError):
    """Raised when `hoctap.toml` or a `HOCTAP_*` variable is invalid."""


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"
    # Read-only folder of source PDFs (the book catalogue's files are relative to it).
    source_dir: Path = REPO_ROOT / "Sach_Arch"
    # Extraction pipeline ([build] table). The model choice is deferred to pilot results.
    extraction_model: str = "claude-opus-5"
    # USD per million tokens (standard prices), for the pre-flight estimate. The real cost
    # of each call is the Claude CLI's own `total_cost_usd`.
    price_input_per_mtok: float = 5.0
    price_output_per_mtok: float = 25.0
    # Page PNGs: the largest scale whose long edge is at most this many pixels.
    render_long_edge: int = 2576
    # The fixed pre-flight estimate per page (two page images + prompt + schema in, over
    # a few tool turns; thinking + JSON out) used before anything is sent.
    estimate_input_tokens_per_page: int = 30000
    estimate_output_tokens_per_page: int = 10000
    # `claude -p` runs: the executable, parallel calls, per-call timeout and budget cap.
    claude_executable: str = "claude"
    extraction_concurrency: int = 3
    extraction_timeout_seconds: int = 900
    extraction_max_budget_usd: float = 1.0
    # A run stops starting new pages once its spend (calls of unknown cost counted at
    # `extraction_max_budget_usd`) reaches this; `hoctap build pilot --max-total-usd`.
    extraction_max_total_usd: float = 10.0
    # The largest page range `hoctap build pilot` accepts.
    pilot_max_pages: int = 30
    # The model of the verify stage's second answer; None (unset) means extraction_model.
    verify_model: str | None = None
    # The go/no-go gate (Story 1.9): the largest share of pilot Problems with a `fallback`
    # Part, the smallest Answer Key accuracy on the spot-check, and the spot-check size.
    gate_max_fallback_share: float = 0.15
    gate_min_key_accuracy: float = 0.98
    gate_min_sample: int = 30
    # HTTPS on the LAN (Story 1.11): the port `serve` binds when an mkcert certificate is
    # present, and the folder `hoctap certs` writes cert.pem/key.pem into.
    tls_port: int = 8443
    tls_cert_dir: Path = REPO_ROOT / "data" / "certs"
    # `hoctap build speak-missing` (Story 2.2): the TTS engine and voice, and the same
    # spend-cap pattern as `extraction_max_total_usd` (edge-tts is free, so this only bounds
    # the cloud engine). The cloud engine's API key is read from the environment only.
    tts_engine: str = "edge-tts"
    tts_voice_id: str = "vi-VN-HoaiMyNeural"
    tts_max_total_usd: float = 5.0

    def __post_init__(self) -> None:
        if self.verify_model is None:
            object.__setattr__(self, "verify_model", self.extraction_model)
        if self.tts_engine not in _TTS_ENGINES:
            raise ConfigError(
                f"tts_engine must be one of {sorted(_TTS_ENGINES)}, got {self.tts_engine!r}"
            )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "hoctap.db"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def build_dir(self) -> Path:
        return self.data_dir / "build"

    @property
    def tls_cert_file(self) -> Path:
        return self.tls_cert_dir / "cert.pem"

    @property
    def tls_key_file(self) -> Path:
        return self.tls_cert_dir / "key.pem"


def _resolve(value: str | Path, base: Path) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else (base / p).resolve()


def validate_port(value: object, source: str) -> int:
    if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
        raise ConfigError(f"{source}: port must be an integer, got {value!r}")
    try:
        port = int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{source}: port must be an integer, got {value!r}") from exc
    if not 0 < port < 65536:
        raise ConfigError(f"{source}: port out of range: {port}")
    return port


def _level(value: object, source: str) -> str:
    level = str(value).upper()
    if level not in _LOG_LEVELS:
        raise ConfigError(f"{source}: log_level must be one of {sorted(_LOG_LEVELS)}")
    return level


# [build] keys: name -> type. Each may also be set as HOCTAP_<NAME> in the environment.
_BUILD_KEYS: dict[str, type] = {
    "extraction_model": str,
    "price_input_per_mtok": float,
    "price_output_per_mtok": float,
    "render_long_edge": int,
    "estimate_input_tokens_per_page": int,
    "estimate_output_tokens_per_page": int,
    "claude_executable": str,
    "extraction_concurrency": int,
    "extraction_timeout_seconds": int,
    "extraction_max_budget_usd": float,
    "extraction_max_total_usd": float,
    "pilot_max_pages": int,
    "verify_model": str,
    "gate_max_fallback_share": float,
    "gate_min_key_accuracy": float,
    "gate_min_sample": int,
    "tts_engine": str,
    "tts_voice_id": str,
    "tts_max_total_usd": float,
}
_POSITIVE = {
    "render_long_edge",
    "extraction_concurrency",
    "extraction_timeout_seconds",
    "extraction_max_budget_usd",
    "extraction_max_total_usd",
    "pilot_max_pages",
    "gate_min_sample",
    "tts_max_total_usd",
}
# Shares: between 0 and 1.
_FRACTIONS = {"gate_max_fallback_share", "gate_min_key_accuracy"}


def _build_value(key: str, value: object, source: str) -> object:
    kind = _BUILD_KEYS[key]
    if kind is str:
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"{source}: {key} must be a non-empty string")
        return value.strip()
    if isinstance(value, bool):
        raise ConfigError(f"{source}: {key} must be a number, got {value!r}")
    try:
        number = kind(value)  # type: ignore[call-arg]
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{source}: {key} must be a number, got {value!r}") from exc
    if not math.isfinite(number):
        raise ConfigError(f"{source}: {key} must be a finite number, got {value!r}")
    if kind is int and isinstance(value, float) and not value.is_integer():
        raise ConfigError(f"{source}: {key} must be an integer, got {value!r}")
    if number < 0 or (key in _POSITIVE and number <= 0):
        raise ConfigError(f"{source}: {key} out of range: {value!r}")
    if key in _FRACTIONS and number > 1:
        raise ConfigError(f"{source}: {key} must be between 0 and 1, got {value!r}")
    return number


def load_settings(config_file: Path | None = None, env: dict[str, str] | None = None) -> Settings:
    env = dict(os.environ) if env is None else env

    if config_file is None:
        if env.get("HOCTAP_CONFIG"):
            config_file = Path(env["HOCTAP_CONFIG"])
            if not config_file.is_file():
                raise ConfigError(f"HOCTAP_CONFIG: file not found: {config_file}")
        else:
            config_file = REPO_ROOT / "hoctap.toml"

    values: dict[str, object] = {
        "data_dir": REPO_ROOT / "data",
        "host": "127.0.0.1",
        "port": 8000,
        "log_level": "INFO",
        "frontend_dist": REPO_ROOT / "frontend" / "dist",
        "source_dir": REPO_ROOT / "Sach_Arch",
        "tls_port": 8443,
        "tls_cert_dir": REPO_ROOT / "data" / "certs",
    }

    if config_file.is_file():
        try:
            with config_file.open("rb") as fh:
                data = tomllib.load(fh)
        except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as exc:
            raise ConfigError(f"{config_file}: {exc}") from exc
        src = str(config_file)
        server = data.get("server", {})
        if not isinstance(server, dict):
            raise ConfigError(f"{src}: [server] must be a table")
        section = server | {k: v for k, v in data.items() if not isinstance(v, dict)}
        base = config_file.resolve().parent
        for key in _PATH_KEYS:
            if key in section:
                if not isinstance(section[key], str):
                    raise ConfigError(f"{src}: {key} must be a string path")
                values[key] = _resolve(section[key], base)
        if "host" in section:
            values["host"] = str(section["host"])
        if "port" in section:
            values["port"] = validate_port(section["port"], src)
        if "log_level" in section:
            values["log_level"] = _level(section["log_level"], src)
        if "tls_port" in section:
            values["tls_port"] = validate_port(section["tls_port"], f"{src}: tls_port")
        build = data.get("build", {})
        if not isinstance(build, dict):
            raise ConfigError(f"{src}: [build] must be a table")
        for key, value in build.items():
            if key not in _BUILD_KEYS:
                raise ConfigError(f"{src}: unknown [build] key {key!r}")
            values[key] = _build_value(key, value, src)

    for key in _PATH_KEYS:
        if env.get(f"HOCTAP_{key.upper()}"):
            values[key] = _resolve(env[f"HOCTAP_{key.upper()}"], REPO_ROOT)
    if env.get("HOCTAP_HOST"):
        values["host"] = env["HOCTAP_HOST"]
    if env.get("HOCTAP_PORT"):
        values["port"] = validate_port(env["HOCTAP_PORT"], "HOCTAP_PORT")
    if env.get("HOCTAP_TLS_PORT"):
        values["tls_port"] = validate_port(env["HOCTAP_TLS_PORT"], "HOCTAP_TLS_PORT")
    if env.get("HOCTAP_LOG_LEVEL"):
        values["log_level"] = _level(env["HOCTAP_LOG_LEVEL"], "HOCTAP_LOG_LEVEL")
    for key in _BUILD_KEYS:
        name = f"HOCTAP_{key.upper()}"
        if env.get(name):
            values[key] = _build_value(key, env[name], name)

    return Settings(**values)  # type: ignore[arg-type]
