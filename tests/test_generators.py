"""Demo checklist and deliverable ZIP bundle tests."""
import zipfile
from io import BytesIO

from pptx import Presentation

from hackpack.generators.bundle import (
    CHECKLIST_FILENAME,
    DECK_FILENAME,
    SCRIPT_FILENAME,
    SUMMARY_FILENAME,
    build_deliverable_zip,
    safe_project_slug,
)
from hackpack.generators.demo_engine import build_demo_plan, generate_demo_checklist
from hackpack.engine.pitch_builder import build_fallback_pitch
from hackpack.models import HackathonBrief, RepoEvidence, TeamContext


def sample_evidence(**kwargs) -> RepoEvidence:
    defaults = dict(
        repo_url="https://github.com/acme/demo",
        repo_name="demo",
        demo_urls=["https://demo.example.org"],
        key_modules=[{"path": "app/main.py", "purpose": "Entry point", "classes": [], "functions": []}],
        test_files=["tests/test_main.py"],
        has_tests=True,
    )
    defaults.update(kwargs)
    return RepoEvidence(**defaults)


def sample_deck():
    return build_fallback_pitch(sample_evidence(), HackathonBrief(), TeamContext())


# --- demo plan --------------------------------------------------------------


def test_demo_plan_only_uses_evidence_backed_steps():
    plan = build_demo_plan(sample_evidence(), sample_deck())
    actions = " ".join(step.action for step in plan.steps)
    assert "https://demo.example.org" in actions
    assert "app/main.py" in actions
    assert "tests/test_main.py" in actions
    assert all(step.evidence_basis for step in plan.steps)


def test_demo_plan_without_evidence_still_usable():
    plan = build_demo_plan(None, sample_deck())
    assert plan.steps
    assert plan.backup_plan
    assert not any("None" in step.action for step in plan.steps)


def test_demo_checklist_markdown_contents():
    plan = build_demo_plan(sample_evidence(), sample_deck())
    checklist = generate_demo_checklist(plan, "Demo")
    assert "# Demo — Demo Checklist" in checklist
    assert "## Before presenting" in checklist
    assert "## Backup plan" in checklist
    assert "Evidence basis" in checklist


# --- bundle -----------------------------------------------------------------


def test_bundle_contains_all_deliverables():
    deck = sample_deck()
    zip_bytes, filename = build_deliverable_zip(deck, evidence=sample_evidence())
    assert filename.endswith("_pitch_pack.zip")
    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        names = set(archive.namelist())
        assert names == {DECK_FILENAME, SCRIPT_FILENAME, CHECKLIST_FILENAME, SUMMARY_FILENAME}
        # The embedded PPTX must reopen cleanly.
        prs = Presentation(BytesIO(archive.read(DECK_FILENAME)))
        assert len(prs.slides) == 6
        script = archive.read(SCRIPT_FILENAME).decode("utf-8")
        assert "Slide 1:" in script
        import json
        summary = json.loads(archive.read(SUMMARY_FILENAME))
        assert summary["slide_count"] == 6
        assert summary["generation_mode"] == "fallback"
        assert summary["app_version"]


def test_safe_project_slug():
    assert safe_project_slug("My Great Project!") == "My_Great_Project"
    assert safe_project_slug("../../etc/passwd") == "etc_passwd"
    assert safe_project_slug("") == "hackpack_pitch"
