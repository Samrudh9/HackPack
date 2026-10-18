"""Pitch builder tests: fallback deck, six-slide enforcement, exact timing."""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from hackpack.engine.pitch_builder import (
    build_fallback_pitch,
    build_pitch,
    ensure_six_slides,
    normalize_timing,
)
from hackpack.llm_client import LLMConfigurationError
from hackpack.models import HackathonBrief, PitchDeck, RepoEvidence, SlideContent, TeamContext


def sample_evidence(**kwargs) -> RepoEvidence:
    defaults = dict(
        repo_url="https://github.com/acme/demo",
        repo_name="demo",
        description="Synthetic demo project",
        file_tree=["app/main.py", "tests/test_main.py"],
        has_tests=True,
        test_files=["tests/test_main.py"],
    )
    defaults.update(kwargs)
    return RepoEvidence(**defaults)


class FailingClient:
    def generate_structured(self, *args, **kwargs):
        raise LLMConfigurationError("model unreachable")


class DeckClient:
    """Returns a valid deck with poor timing that normalization must fix."""

    def __init__(self):
        self.calls = 0

    def generate_structured(self, system_prompt, user_prompt, response_model, temperature=0.1):
        self.calls += 1
        return PitchDeck(
            project_name="AI Project",
            tagline="From the model",
            slides=[
                SlideContent(slide_number=i, title=f"Slide {i}", bullet_points=["point"], speaking_time_seconds=200 if i == 1 else 10)
                for i in range(1, 7)
            ],
            total_duration_seconds=250,
        )


# --- fallback ---------------------------------------------------------------


def test_fallback_pitch_is_six_slides_and_labelled():
    deck = build_fallback_pitch(sample_evidence(), HackathonBrief(pitch_duration_minutes=3), TeamContext())
    assert len(deck.slides) == 6
    assert deck.generation_mode == "fallback"
    assert deck.generation_warnings
    assert deck.total_duration_seconds == 180
    assert sum(s.speaking_time_seconds for s in deck.slides) == 180


def test_fallback_pitch_uses_repo_facts_without_inventing_metrics():
    evidence = sample_evidence(
        tech_stack=[],
        source_excerpts={},
        readme_content=None,
    )
    team = TeamContext(
        problem_statement="Small clinics lose hours to manual intake.",
        target_users="Clinic administrative staff",
    )
    deck = build_fallback_pitch(evidence, HackathonBrief(pitch_duration_minutes=5), team)
    all_bullets = " ".join(b for slide in deck.slides for b in slide.bullet_points)
    assert "demo" in all_bullets  # repo name appears
    assert "Small clinics" in all_bullets  # team problem included
    # No fabricated numbers or metrics anywhere in the deck.
    for banned in ("%", "5000", "accuracy", "revenue"):
        assert banned not in all_bullets.lower()


def test_fallback_flags_missing_team_input():
    deck = build_fallback_pitch(sample_evidence(), HackathonBrief(), TeamContext())
    assert any("not provided" in b.lower() or "not specified" in b.lower() or "not described" in b.lower()
               for slide in deck.slides for b in slide.bullet_points)


# --- AI path post-processing ------------------------------------------------


def test_build_pitch_normalizes_model_output():
    client = DeckClient()
    deck = build_pitch(sample_evidence(), HackathonBrief(pitch_duration_minutes=2), TeamContext(), client=client)
    assert client.calls == 1
    assert len(deck.slides) == 6
    assert deck.generation_mode == "ai"
    assert sum(s.speaking_time_seconds for s in deck.slides) == 120
    assert [s.slide_number for s in deck.slides] == [1, 2, 3, 4, 5, 6]


def test_build_pitch_falls_back_when_model_unavailable():
    deck = build_pitch(sample_evidence(), HackathonBrief(), TeamContext(), client=FailingClient())
    assert deck.generation_mode == "fallback"
    assert len(deck.slides) == 6


# --- timing -----------------------------------------------------------------


@pytest.mark.parametrize("minutes", [1, 2, 3, 7, 10])
def test_timing_sums_exactly_to_requested_duration(minutes):
    deck = build_fallback_pitch(sample_evidence(), HackathonBrief(pitch_duration_minutes=minutes), TeamContext())
    assert sum(s.speaking_time_seconds for s in deck.slides) == minutes * 60
    assert all(s.speaking_time_seconds >= 5 for s in deck.slides)


def test_normalize_timing_respects_minimums():
    # model_construct bypasses field validation so we can feed pathological timings.
    deck = PitchDeck.model_construct(
        project_name="X", tagline="Y",
        slides=[
            SlideContent(slide_number=i, title=f"S{i}", speaking_time_seconds=5 if i < 6 else 900)
            for i in range(1, 7)
        ],
        total_duration_seconds=400,
    )
    deck = normalize_timing(deck, 60)
    assert sum(s.speaking_time_seconds for s in deck.slides) == 60
    assert all(s.speaking_time_seconds >= 5 for s in deck.slides)


def test_ensure_six_slides_keeps_existing_titles():
    deck = PitchDeck.model_construct(
        project_name="X", tagline="Y",
        slides=[SlideContent(slide_number=1, title="Custom opening", bullet_points=["a"])],
        total_duration_seconds=180,
    )
    deck = ensure_six_slides(deck)
    assert len(deck.slides) == 6
    assert deck.slides[0].title == "Custom opening"
