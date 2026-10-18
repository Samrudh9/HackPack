"""HackPack Streamlit MVP: repository -> evidence -> pitch pack."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from config import settings
from hackpack.models import HackathonBrief, TeamContext, EvidenceType
from hackpack.engine.repo_analyzer import analyze_repository, RepositoryAnalysisError
from hackpack.engine.evidence_store import summarize_evidence
from hackpack.engine.pitch_builder import build_pitch
from hackpack.engine.verifier import verify_claims
from hackpack.generators.pptx_engine import generate_pptx
from hackpack.generators.script_engine import generate_script
from hackpack.generators.demo_engine import build_demo_plan, generate_demo_checklist
from hackpack.generators.pdf_export import convert_pptx_to_pdf, PDFExportUnavailable
from hackpack.llm_client import LLMClient, LLMConfigurationError

st.set_page_config(page_title="HackPack — Hackathon Pitch Assistant", page_icon="🎒", layout="wide")
st.title("🎒 HackPack")
st.subheader("Turn what you built into a pitch you can present.")
st.caption("Open-source · Local-model friendly · Any hackathon domain · Evidence-aware")

with st.sidebar:
    st.header("Your pitch")
    st.write("Start with a public GitHub repository. Add the event brief and team context to help HackPack tell the right story.")
    pitch_duration = st.slider("Pitch duration (minutes)", min_value=1, max_value=10, value=settings.DEFAULT_PITCH_DURATION_MINUTES)
    st.divider()
    st.caption(f"Configured model: `{settings.LLM_MODEL}`")
    if settings.LLM_MODEL.startswith("ollama/"):
        st.caption("Local mode requires Ollama running on this machine.")

with st.form("hackpack_inputs"):
    st.subheader("1. Project and event")
    repo_url = st.text_input("Public GitHub repository URL", placeholder="https://github.com/owner/repository")
    col_a, col_b = st.columns(2)
    with col_a:
        event_name = st.text_input("Hackathon name (optional)", placeholder="Open Innovation Hackathon")
        theme = st.text_input("Theme or challenge (optional)", placeholder="Any domain or problem area")
    with col_b:
        judging_raw = st.text_area("Judging criteria (optional)", placeholder="Innovation, technical execution, impact, demo…", height=100)
        additional_rules = st.text_input("Required format or rules (optional)", placeholder="3-minute pitch, must show prototype")

    st.subheader("2. Context only your team knows")
    col_c, col_d = st.columns(2)
    with col_c:
        problem_statement = st.text_area("Problem you're solving", placeholder="Who has what problem, and why does it matter?", height=100)
        target_users = st.text_area("Who is this for?", placeholder="Target users, customers, or beneficiaries", height=80)
    with col_d:
        key_results = st.text_area("What works today? (optional)", placeholder="Features you personally verified, tests run, user feedback…", height=100)
        impact_claims_raw = st.text_area("Metrics or impact claims (optional)", placeholder="Any numbers will be flagged unless evidence supports them.", height=80)
    future_plans = st.text_input("Next steps (optional)", placeholder="What you would build or validate next")
    team_members_raw = st.text_input("Team members (optional; comma-separated)")
    analyze_clicked = st.form_submit_button("Analyze repository", type="primary", use_container_width=True)

if analyze_clicked:
    if not repo_url.strip():
        st.error("Enter a public GitHub repository URL first.")
    else:
        with st.spinner("Reading repository metadata and selected source files…"):
            try:
                evidence = analyze_repository(repo_url.strip())
                st.session_state["hackpack_evidence"] = evidence
                st.session_state["hackpack_repo_url"] = repo_url.strip()
                st.session_state.pop("hackpack_output", None)
                st.session_state["hackpack_context"] = {
                    "pitch_duration": pitch_duration,
                    "event_name": event_name,
                    "theme": theme,
                    "judging_criteria": judging_raw,
                    "additional_rules": additional_rules,
                    "problem_statement": problem_statement,
                    "target_users": target_users,
                    "key_results": key_results,
                    "impact_claims": impact_claims_raw,
                    "future_plans": future_plans,
                    "team_members": team_members_raw,
                }
            except RepositoryAnalysisError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Repository analysis failed ({type(exc).__name__}). Check the URL and retry.")

evidence = st.session_state.get("hackpack_evidence")
if evidence is not None:
    st.divider()
    st.subheader("3. Review what HackPack found")
    summary = summarize_evidence(evidence)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Files in repository", evidence.total_files)
    k2.metric("Technologies found", len(evidence.tech_stack))
    k3.metric("Key Python modules", len(evidence.key_modules))
    k4.metric("Tests detected", "Yes" if evidence.has_tests else "Not detected")
    if evidence.description:
        st.write(evidence.description)
    if evidence.analysis_warnings:
        for warning in evidence.analysis_warnings:
            st.warning(warning)
    with st.expander("Detected technologies", expanded=True):
        if evidence.tech_stack:
            st.dataframe([item.model_dump() for item in evidence.tech_stack[:40]], use_container_width=True, hide_index=True)
        else:
            st.info("No supported dependency manifests were detected. The source files can still be used to draft the pitch.")
    with st.expander("Key modules and repository facts"):
        st.json({
            "primary_language": evidence.primary_language,
            "languages": evidence.languages,
            "has_ci": evidence.has_ci,
            "has_docker": evidence.has_docker,
            "has_demo": evidence.has_demo,
            "demo_urls": evidence.demo_urls,
            "key_modules": evidence.key_modules,
        })
    with st.expander("Analyzed file list (first 150 paths)"):
        st.code("\n".join(evidence.file_tree[:150]) or "No files found")

    if st.button("Generate pitch pack", type="primary", use_container_width=True):
        context = st.session_state.get("hackpack_context", {})
        brief = HackathonBrief(
            event_name=context.get("event_name") or "Hackathon",
            theme=context.get("theme") or None,
            judging_criteria=[line.strip(" •-\t") for line in context.get("judging_criteria", "").splitlines() if line.strip(" •-\t")],
            pitch_duration_minutes=int(context.get("pitch_duration", settings.DEFAULT_PITCH_DURATION_MINUTES)),
            required_deliverables=[],
            additional_rules=context.get("additional_rules") or None,
        )
        team = TeamContext(
            problem_statement=context.get("problem_statement", ""),
            target_users=context.get("target_users", ""),
            key_results=context.get("key_results") or None,
            impact_claims=[line.strip(" •-\t") for line in context.get("impact_claims", "").splitlines() if line.strip(" •-\t")],
            future_plans=context.get("future_plans") or None,
            team_members=[name.strip() for name in context.get("team_members", "").split(",") if name.strip()],
        )
        try:
            with st.spinner("Building a project-specific pitch and checking claims…"):
                deck = build_pitch(evidence, brief, team, client=LLMClient())
                deck = verify_claims(deck, evidence, team)
                pptx_bytes = generate_pptx(deck)
                script = generate_script(deck)
                demo_plan = build_demo_plan(evidence, deck, demo_duration_seconds=min(300, brief.pitch_duration_minutes * 60))
                checklist = generate_demo_checklist(demo_plan, deck.project_name)
                output = {
                    "deck": deck,
                    "pptx": pptx_bytes,
                    "script": script,
                    "checklist": checklist,
                    "brief": brief,
                }
                st.session_state["hackpack_output"] = output
        except LLMConfigurationError as exc:
            st.error(str(exc))
            if settings.LLM_MODEL.startswith("ollama/"):
                st.code("ollama pull llama3.1\nollama serve", language="bash")
        except Exception as exc:
            st.error(f"Generation failed ({type(exc).__name__}). Try a smaller repository or a model with stronger JSON output support.")

output = st.session_state.get("hackpack_output")
if output:
    deck = output["deck"]
    st.divider()
    st.subheader("4. Your pitch pack is ready")
    st.success(f"Generated {len(deck.slides)} slides for {deck.project_name} · target duration {deck.total_duration_seconds // 60}:{deck.total_duration_seconds % 60:02d}")
    if deck.generation_mode == "fallback":
        st.warning(
            "This deck was produced by the deterministic template fallback because the AI model was "
            "unavailable or returned invalid output. Review and personalize every slide before presenting."
        )
        for gen_warning in deck.generation_warnings:
            st.caption(gen_warning)
    all_claims = [claim for slide in deck.slides for claim in slide.claims]
    unverified = [claim for claim in all_claims if claim.evidence_type == EvidenceType.NEEDS_VERIFICATION]
    c1, c2, c3 = st.columns(3)
    c1.metric("Slides", len(deck.slides))
    c2.metric("Claims to review", len(unverified))
    c3.metric("Source files analyzed", len(evidence.source_excerpts))

    with st.expander("Preview slide content", expanded=True):
        for slide in deck.slides:
            st.markdown(f"### {slide.slide_number}. {slide.title}")
            if slide.subtitle:
                st.caption(slide.subtitle)
            for bullet in slide.bullet_points:
                st.markdown(f"- {bullet}")
            st.caption(f"{slide.speaking_time_seconds} seconds · {slide.speaker_notes[:260]}")
            for claim in slide.claims:
                st.caption(f"Claim status: {claim.evidence_type.value} · Source: {claim.source or 'not provided'}")
            st.markdown("---")
    if deck.unverified_claims:
        st.warning("Some claims need confirmation. Review them before presenting.")
        st.dataframe([
            {"Claim": claim.statement, "Status": claim.evidence_type.value, "Source": claim.source or "—", "Action": claim.needs_action or "—"}
            for claim in deck.unverified_claims
        ], use_container_width=True, hide_index=True)

    filename = "".join(c if c.isalnum() or c in "-_" else "_" for c in deck.project_name).strip("_") or "hackpack_pitch"
    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button("Download PowerPoint (.pptx)", data=output["pptx"], file_name=f"{filename}_pitch.pptx", mime="application/vnd.openxmlformats-officedocument.presentationml.presentation", use_container_width=True)
    with col2:
        st.download_button("Download pitch script (.md)", data=output["script"], file_name=f"{filename}_pitch_script.md", mime="text/markdown", use_container_width=True)
    with col3:
        st.download_button("Download demo checklist (.md)", data=output["checklist"], file_name=f"{filename}_demo_checklist.md", mime="text/markdown", use_container_width=True)

    try:
        pdf_bytes = convert_pptx_to_pdf(output["pptx"])
        st.download_button("Download PDF version", data=pdf_bytes, file_name=f"{filename}_pitch.pdf", mime="application/pdf")
    except PDFExportUnavailable as exc:
        st.caption(str(exc))

st.divider()
st.caption("HackPack v0.1 · Repository code is treated as untrusted data and never executed. Review generated content before presenting.")
