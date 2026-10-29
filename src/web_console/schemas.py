"""Request bodies accepted by the console API (validated by Pydantic; unknown fields are rejected)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Mode = Literal["prompt", "hosted", "local", "cua"]
NAME = r"^[A-Za-z0-9._-]+$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Adhoc(Strict):
    url: str = Field(max_length=2000)
    task: str = Field(min_length=1, max_length=8000)


class Options(Strict):
    remote_browser: bool = False  # local mode: cloud browser through the toolbox instead of Playwright MCP
    headed: bool = False  # local mode and Computer Use: show the browser window on this PC
    auto_ack: bool = False  # Computer Use: acknowledge safety checks automatically (demo only)
    mirror: bool = True  # local mode: screenshots of the agent's browser in the console


class RenderRequest(Strict):
    scenario_id: str | None = Field(default=None, max_length=80, pattern=NAME)
    adhoc: Adhoc | None = None
    url: str | None = Field(default=None, max_length=2000)
    inputs: dict[str, Any] | None = None
    inputs_yaml: str | None = Field(default=None, max_length=20000)
    site_url: str | None = Field(default=None, max_length=500)
    modes: list[Mode] = Field(default_factory=list, max_length=4)
    options: Options = Field(default_factory=Options)


class JobRequest(RenderRequest):
    modes: list[Mode] = Field(min_length=1, max_length=4)
    prompt_model: str | None = Field(default=None, max_length=64, pattern=NAME)
    cua_model: str | None = Field(default=None, max_length=64, pattern=NAME)

    @field_validator("modes")
    @classmethod
    def unique_modes(cls, modes: list[str]) -> list[str]:
        if len(set(modes)) != len(modes):
            raise ValueError("each mode can only be selected once")
        return modes
