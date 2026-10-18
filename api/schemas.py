"""Pydantic request/response schemas for the HackPack REST API.

Response models reuse the core ``hackpack.models`` contracts so the API, the
library, and the frontend always agree on one schema.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from hackpack.models import HackathonBrief, PitchDeck, RepoEvidence, TeamContext


class HealthResponse(BaseModel):
    status: str = "ok"
    app: str
    version: str
    llm_model: str
    llm_fallback_enabled: bool
    default_pitch_duration_minutes: int


class AnalyzeRequest(BaseModel):
    repo_url: str = Field(
        min_length=12,
        max_length=300,
        description="Public GitHub repository URL, e.g. https://github.com/owner/repo",
        examples=["https://github.com/owner/repository"],
    )


class AnalyzeResponse(BaseModel):
    evidence: RepoEvidence
    summary: dict


class PitchRequest(BaseModel):
    evidence: RepoEvidence
    brief: HackathonBrief = Field(default_factory=HackathonBrief)
    team: TeamContext = Field(default_factory=TeamContext)


class PitchResponse(BaseModel):
    deck: PitchDeck
    generation_mode: str
    warnings: list[str] = Field(default_factory=list)


class GenerateRequest(BaseModel):
    deck: PitchDeck
    evidence: Optional[RepoEvidence] = None
    demo_duration_seconds: int = Field(default=180, ge=30, le=900)


class ErrorResponse(BaseModel):
    detail: str
