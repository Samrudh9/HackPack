"""Create a timed, editable Markdown pitch script from a generated deck."""
from hackpack.models import PitchDeck


def _timestamp(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def generate_script(deck: PitchDeck) -> str:
    lines = [
        f"# {deck.project_name} — Hackathon Pitch Script",
        "",
        f"**Target duration:** {deck.total_duration_seconds // 60} min {deck.total_duration_seconds % 60:02d} sec  ",
        f"**Tagline:** {deck.tagline}  ",
        f"**Generation mode:** {deck.generation_mode}"
        + (" — review every slide carefully; this deck came from the deterministic fallback." if deck.generation_mode == "fallback" else ""),
        "",
        "> Review every technical and impact claim before presenting. Statements marked for verification should not be presented as proven results.",
        "",
    ]
    if deck.generation_warnings:
        lines.extend(["**Generation warnings**"])
        lines.extend(f"- {warning}" for warning in deck.generation_warnings)
        lines.append("")

    current = 0
    for slide in deck.slides:
        end = current + slide.speaking_time_seconds
        lines.extend([
            f"## Slide {slide.slide_number}: {slide.title} [{_timestamp(current)}–{_timestamp(end)}]",
            "",
            slide.speaker_notes.strip() or "Use the slide bullets to explain this section in your own words.",
            "",
        ])
        if slide.subtitle:
            lines.append(f"**Subtitle on slide:** {slide.subtitle}")
            lines.append("")
        if slide.bullet_points:
            lines.append("**Key points**")
            lines.extend([f"- {point}" for point in slide.bullet_points])
            lines.append("")

        evidence_sources = [
            claim for claim in slide.claims
            if claim.source and claim.evidence_type.value in {"repo_evidence", "test_evidence_found"}
        ]
        if evidence_sources:
            lines.append("**Evidence references**")
            for claim in evidence_sources:
                location = f"`{claim.source}`"
                if claim.line_start:
                    location += f" (around line {claim.line_start})"
                lines.append(f"- {claim.statement} — {location} [{claim.evidence_type.value}]")
            lines.append("")

        flagged = [claim for claim in slide.claims if claim.needs_action]
        if flagged:
            lines.append("**Review before presenting**")
            lines.extend([f"- {claim.statement} — {claim.needs_action}" for claim in flagged])
            lines.append("")
        lines.append("---")
        lines.append("")
        current = end
    lines.append(f"**Total timed duration:** {_timestamp(current)}")
    return "\n".join(lines).rstrip() + "\n"
