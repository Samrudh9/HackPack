"""Typed data contracts shared by HackPack's analysis and generation pipeline.

All models use Pydantic v2 conventions. Mutable collections always use
``Field(default_factory=...)`` so instances never share state.
"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator

# Hard caps that protect slide readability and prompt size. These are part of
# the v0.1 product contract: the deck always contains exactly six slides.
SLIDE_COUNT = 6
MAX_BULLETS_PER_SLIDE = 5
MAX_STATEMENT_CHARS = 400
MAX_BULLET_CHARS = 220


class EvidenceType(str, Enum):
    """How strongly a claim is grounded. An LLM label is never treated as proof."""

    REPO_EVIDENCE = "repo_evidence"
    TEST_EVIDENCE_FOUND = "test_evidence_found"
    TEAM_PROVIDED = "team_provided"
    INFERRED = "inferred"
    NEEDS_VERIFICATION = "needs_verification"


class ClaimCategory(str, Enum):
    """Coarse claim type used to choose the right verification strategy."""

    IMPLEMENTATION = "implementation_feature"
    TECHNOLOGY = "technology_usage"
    DEPLOYMENT = "deployment"
    NUMERICAL_METRIC = "numerical_metric"
    USER_COUNT = "user_count"
    PERFORMANCE = "performance_result"
    OTHER = "other"


class EvidenceCandidate(BaseModel):
    """A piece of repository content retrieved while checking a claim.

    This records where the evidence was found; it does not assert that the
    claim is true. Excerpts are short, redacted, and never executed.
    """

    path: str = Field(min_length=1, max_length=400)
    excerpt: str = Field(default="", max_length=600)
    line_start: Optional[int] = Field(default=None, ge=1)
    line_end: Optional[int] = Field(default=None, ge=1)
    note: str = Field(default="", max_length=300)

    @field_validator("line_end")
    @classmethod
    def line_end_not_before_start(cls, value, info):
        if value is not None and info.data.get("line_start") and value < info.data["line_start"]:
            raise ValueError("line_end must not be before line_start")
        return value


class TechStackItem(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    version: Optional[str] = Field(default=None, max_length=60)
    category: str = Field(default="library", max_length=60)
    evidence_file: str = Field(min_length=1, max_length=400)


class RepoEvidence(BaseModel):
    """Structured facts gathered from a public repository without executing it."""

    repo_url: str = Field(min_length=1, max_length=300)
    repo_name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    readme_content: Optional[str] = None
    file_tree: list[str] = Field(default_factory=list, max_length=2000)
    tech_stack: list[TechStackItem] = Field(default_factory=list, max_length=300)
    key_modules: list[dict] = Field(default_factory=list, max_length=60)
    test_files: list[str] = Field(default_factory=list, max_length=200)
    test_excerpts: dict[str, str] = Field(default_factory=dict)
    has_tests: bool = False
    has_ci: bool = False
    has_docker: bool = False
    has_demo: bool = False
    demo_urls: list[str] = Field(default_factory=list, max_length=30)
    license: Optional[str] = Field(default=None, max_length=120)
    total_files: int = Field(default=0, ge=0)
    primary_language: Optional[str] = Field(default=None, max_length=80)
    languages: dict[str, int] = Field(default_factory=dict)
    # Kept short and redacted. Used as evidence, not executed.
    source_excerpts: dict[str, str] = Field(default_factory=dict)
    analysis_warnings: list[str] = Field(default_factory=list, max_length=50)


class HackathonBrief(BaseModel):
    event_name: str = Field(default="Hackathon", min_length=1, max_length=200)
    theme: Optional[str] = Field(default=None, max_length=400)
    judging_criteria: list[str] = Field(default_factory=list, max_length=20)
    pitch_duration_minutes: int = Field(default=3, ge=1, le=20)
    required_deliverables: list[str] = Field(default_factory=list, max_length=20)
    additional_rules: Optional[str] = Field(default=None, max_length=1000)


class TeamContext(BaseModel):
    problem_statement: str = Field(default="", max_length=2000)
    target_users: str = Field(default="", max_length=1000)
    key_results: Optional[str] = Field(default=None, max_length=2000)
    impact_claims: list[str] = Field(default_factory=list, max_length=20)
    future_plans: Optional[str] = Field(default=None, max_length=1500)
    team_members: list[str] = Field(default_factory=list, max_length=20)


class Claim(BaseModel):
    """An assertion made in the pitch, plus how well it is grounded.

    ``evidence_type`` is produced by deterministic verification code, never
    trusted from an LLM's self-report.
    """

    statement: str = Field(min_length=1, max_length=MAX_STATEMENT_CHARS)
    category: ClaimCategory = ClaimCategory.OTHER
    evidence_type: EvidenceType = EvidenceType.INFERRED
    source: Optional[str] = Field(default=None, max_length=400)
    line_start: Optional[int] = Field(default=None, ge=1)
    line_end: Optional[int] = Field(default=None, ge=1)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    needs_action: Optional[str] = Field(default=None, max_length=500)
    candidates: list[EvidenceCandidate] = Field(default_factory=list, max_length=8)


class SlideContent(BaseModel):
    slide_number: int = Field(ge=1, le=SLIDE_COUNT)
    title: str = Field(min_length=1, max_length=120)
    subtitle: Optional[str] = Field(default=None, max_length=240)
    bullet_points: list[str] = Field(default_factory=list, max_length=MAX_BULLETS_PER_SLIDE)
    speaker_notes: str = Field(default="", max_length=4000)
    speaking_time_seconds: int = Field(default=30, ge=5, le=900)
    claims: list[Claim] = Field(default_factory=list, max_length=30)

    @field_validator("bullet_points")
    @classmethod
    def bullets_are_bounded_and_non_empty(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for bullet in value:
            text = " ".join(str(bullet).split())
            if not text:
                continue
            if len(text) > MAX_BULLET_CHARS:
                text = text[: MAX_BULLET_CHARS - 3].rstrip() + "..."
            cleaned.append(text)
        if len(cleaned) > MAX_BULLETS_PER_SLIDE:
            cleaned = cleaned[:MAX_BULLETS_PER_SLIDE]
        return cleaned


class PitchDeck(BaseModel):
    project_name: str = Field(min_length=1, max_length=200)
    tagline: str = Field(default="A hackathon project", min_length=1, max_length=300)
    # v0.1 always presents exactly six slides.
    slides: list[SlideContent] = Field(min_length=SLIDE_COUNT, max_length=SLIDE_COUNT)
    total_duration_seconds: int = Field(default=180, ge=30, le=1500)
    # "ai" = model-generated (then verified); "fallback" = deterministic template.
    generation_mode: str = Field(default="ai", pattern="^(ai|fallback)$")
    generation_warnings: list[str] = Field(default_factory=list, max_length=30)
    unverified_claims: list[Claim] = Field(default_factory=list, max_length=100)

    @field_validator("project_name", "tagline")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be empty")
        return value


class DemoStep(BaseModel):
    order: int = Field(ge=1)
    action: str = Field(min_length=1, max_length=500)
    expected_result: str = Field(min_length=1, max_length=500)
    talking_point: str = Field(min_length=1, max_length=500)
    estimated_seconds: int = Field(default=30, ge=5, le=600)
    requires: Optional[str] = Field(default=None, max_length=400)
    evidence_basis: Optional[str] = Field(default=None, max_length=400)


class DemoPlan(BaseModel):
    steps: list[DemoStep] = Field(default_factory=list, max_length=20)
    prerequisites: list[str] = Field(default_factory=list, max_length=30)
    total_duration_seconds: int = Field(default=0, ge=0)
    backup_plan: str = Field(default="", max_length=1000)
