"""Package the deliverables (PPTX, script, checklist, summary) into one ZIP.

The ZIP is built entirely in memory: no server-side paths are derived from
client input, so there is no path-traversal surface. Entry names are fixed.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime, timezone

from config import settings
from hackpack.models import PitchDeck, RepoEvidence
from hackpack.generators.pptx_engine import generate_pptx
from hackpack.generators.script_engine import generate_script
from hackpack.generators.demo_engine import build_demo_plan, generate_demo_checklist

DECK_FILENAME = "pitch_deck.pptx"
SCRIPT_FILENAME = "pitch_script.md"
CHECKLIST_FILENAME = "demo_checklist.md"
SUMMARY_FILENAME = "generation_summary.json"


def safe_project_slug(project_name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9\-_]+", "_", project_name).strip("_")
    return slug[:60] or "hackpack_pitch"


def build_generation_summary(
    deck: PitchDeck,
    evidence: RepoEvidence | None,
    warnings: list[str] | None = None,
) -> dict:
    flagged = [
        {
            "statement": claim.statement,
            "status": claim.evidence_type.value,
            "source": claim.source,
            "action": claim.needs_action,
        }
        for claim in deck.unverified_claims
    ]
    summary = {
        "app": settings.APP_NAME,
        "app_version": settings.APP_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "project_name": deck.project_name,
        "slide_count": len(deck.slides),
        "total_duration_seconds": deck.total_duration_seconds,
        "generation_mode": deck.generation_mode,
        "generation_warnings": list(deck.generation_warnings) + list(warnings or []),
        "flagged_claims": flagged,
        "notice": (
            "Generated content is a draft. Repository analysis and claim checks are "
            "heuristic and do not prove runtime behaviour. Review before presenting."
        ),
    }
    if evidence is not None:
        summary["repository"] = {
            "url": evidence.repo_url,
            "primary_language": evidence.primary_language,
            "files_inspected": len(evidence.source_excerpts),
            "tests_detected": evidence.has_tests,
            "analysis_warnings": evidence.analysis_warnings,
        }
    return summary


def build_deliverable_zip(
    deck: PitchDeck,
    evidence: RepoEvidence | None = None,
    demo_duration_seconds: int = 180,
    extra_warnings: list[str] | None = None,
) -> tuple[bytes, str]:
    """Return ``(zip_bytes, zip_filename)`` containing all v0.1 deliverables."""
    pptx_bytes = generate_pptx(deck)
    script = generate_script(deck)
    plan = build_demo_plan(evidence, deck, demo_duration_seconds=demo_duration_seconds)
    checklist = generate_demo_checklist(plan, deck.project_name)
    summary = build_generation_summary(deck, evidence, extra_warnings)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(DECK_FILENAME, pptx_bytes)
        archive.writestr(SCRIPT_FILENAME, script)
        archive.writestr(CHECKLIST_FILENAME, checklist)
        archive.writestr(
            SUMMARY_FILENAME,
            json.dumps(summary, indent=2, ensure_ascii=False),
        )
    slug = safe_project_slug(deck.project_name)
    return buffer.getvalue(), f"{slug}_pitch_pack.zip"
