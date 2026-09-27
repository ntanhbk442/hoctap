"""Request and response models for setup, PIN login and Child Profiles."""

from __future__ import annotations

import unicodedata
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AVATARS: tuple[str, ...] = ("cat", "dog", "rabbit", "bear", "fox", "panda")
Avatar = Literal["cat", "dog", "rabbit", "bear", "fox", "panda"]

# `[0-9]`, not `\d`: `\d` also matches non-ASCII digits.
Pin = Annotated[str, Field(pattern=r"^[0-9]{4}$")]

NAME_MAX = 40


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    avatar: Avatar
    grade: int = Field(ge=1, le=5)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        value = unicodedata.normalize("NFC", value)
        # Control, format (e.g. U+200B, U+FEFF), surrogate, private and unassigned chars.
        if any(unicodedata.category(ch).startswith("C") for ch in value):
            raise ValueError("name contains control or invisible characters")
        value = value.strip()
        if not any(ch.isprintable() and not ch.isspace() for ch in value):
            raise ValueError("name is empty")
        if len(value) > NAME_MAX:
            raise ValueError("name too long")
        return value


class SetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pin: Pin
    pin_confirm: Pin
    profile: ProfileIn


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pin: Pin


class Profile(BaseModel):
    id: str
    name: str
    avatar: Avatar
    grade: int


class SetupStatus(BaseModel):
    setup_required: bool


class SessionStatus(BaseModel):
    authenticated: Literal[True]
