import pytest
from pydantic import ValidationError
from hackpack.models import (
    Claim,
    ClaimCategory,
    EvidenceCandidate,
    EvidenceType,
    HackathonBrief,
    PitchDeck,
    RepoEvidence,
    SlideContent,
)


def make_slide(number: int, **kwargs) -> SlideContent:
    defaults = dict(
        slide_number=number,
        title=f"Slide {number}",
        bullet_points=["Example detail"],
        speaker_notes="Explain the point.",
    )
    defaults.update(kwargs)
    return SlideContent(**defaults)


def test_pitch_deck_model_accepts_valid_six_slide_deck():
    deck = PitchDeck(
        project_name="Example",
        tagline="A useful prototype",
        slides=[make_slide(i) for i in range(1, 7)],
        total_duration_seconds=180,
    )
    assert len(deck.slides) == 6
    assert deck.total_duration_seconds == 180
    assert deck.generation_mode == "ai"


def test_pitch_deck_requires_exactly_six_slides():
    with pytest.raises(ValidationError):
        PitchDeck(
            project_name="Example",
            tagline="A useful prototype",
            slides=[make_slide(i) for i in range(1, 5)],
            total_duration_seconds=120,
        )


def test_hackathon_duration_bounds():
    assert HackathonBrief(pitch_duration_minutes=3).pitch_duration_minutes == 3
    with pytest.raises(ValidationError):
        HackathonBrief(pitch_duration_minutes=0)
    with pytest.raises(ValidationError):
        HackathonBrief(pitch_duration_minutes=21)


def test_claim_defaults_are_conservative():
    claim = Claim(statement="An unverified claim")
    assert claim.evidence_type == EvidenceType.INFERRED
    assert claim.category == ClaimCategory.OTHER
    assert claim.candidates == []


def test_evidence_enum_contains_required_classifications():
    values = {member.value for member in EvidenceType}
    assert {"repo_evidence", "test_evidence_found", "team_provided", "inferred", "needs_verification"} <= values


def test_claim_line_range_must_be_ordered():
    with pytest.raises(ValidationError):
        EvidenceCandidate(path="src/app.py", line_start=10, line_end=5)


def test_slide_bullets_are_bounded():
    slide = make_slide(1, bullet_points=["a" * 400, "short one", "", "  "])
    assert len(slide.bullet_points) == 2
    assert len(slide.bullet_points[0]) <= 220


def test_generation_mode_is_restricted():
    with pytest.raises(ValidationError):
        PitchDeck(
            project_name="X", tagline="Y",
            slides=[make_slide(i) for i in range(1, 7)],
            generation_mode="quantum",
        )


def test_repo_evidence_requires_identity():
    with pytest.raises(ValidationError):
        RepoEvidence(repo_url="", repo_name="demo")
