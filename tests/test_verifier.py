"""Conservative claim verification tests."""
from hackpack.models import (
    Claim,
    ClaimCategory,
    EvidenceType,
    PitchDeck,
    RepoEvidence,
    SlideContent,
    TeamContext,
)
from hackpack.engine.verifier import categorize_claim, retrieve_candidates, verify_claim, verify_claims


def sample_evidence(**kwargs) -> RepoEvidence:
    defaults = dict(repo_url="https://github.com/acme/demo", repo_name="demo")
    defaults.update(kwargs)
    return RepoEvidence(**defaults)


def sample_deck(claim) -> PitchDeck:
    return PitchDeck(
        project_name="Demo", tagline="A demo project",
        slides=[SlideContent(slide_number=i, title=f"Slide {i}", bullet_points=["Point"], claims=[claim]) for i in range(1, 7)],
        total_duration_seconds=180,
    )


# --- categorisation ---------------------------------------------------------


def test_claim_categorisation():
    assert categorize_claim("The model achieves 95% accuracy") == ClaimCategory.NUMERICAL_METRIC
    assert categorize_claim("We have 5000 active users") == ClaimCategory.USER_COUNT
    assert categorize_claim("The app is deployed in production") == ClaimCategory.DEPLOYMENT
    assert categorize_claim("Response latency is 120ms") == ClaimCategory.PERFORMANCE
    assert categorize_claim("Built with FastAPI for the backend") == ClaimCategory.TECHNOLOGY
    assert categorize_claim("Parses PDF invoices with a custom parser") == ClaimCategory.IMPLEMENTATION


# --- metric claims ----------------------------------------------------------


def test_unsupported_metric_is_flagged():
    evidence = sample_evidence(source_excerpts={})
    claim = Claim(statement="The model achieves 95% accuracy", source="src/model.py")
    deck = verify_claims(sample_deck(claim), evidence, TeamContext())
    assert deck.slides[0].claims[0].evidence_type == EvidenceType.NEEDS_VERIFICATION
    assert deck.slides[0].claims[0].needs_action
    assert deck.unverified_claims


def test_unrelated_number_match_does_not_verify_metric():
    # "95" exists in the repo but in an unrelated context (no metric name nearby).
    evidence = sample_evidence(
        source_excerpts={"src/utils.py": "def helper():\n    # see issue 95 for details\n    return None\n"},
    )
    claim = Claim(statement="The model achieves 95% accuracy")
    verified = verify_claim(claim, evidence)
    assert verified.evidence_type == EvidenceType.NEEDS_VERIFICATION


def test_number_with_metric_in_source_but_no_eval_context():
    # Accuracy + 95 appear together in ordinary source, not a test/eval artifact.
    content = "accuracy = compute_accuracy(model)\n# previous best was 95 on the dev set\n"
    evidence = sample_evidence(source_excerpts={"src/model.py": content})
    claim = Claim(statement="The model achieves 95% accuracy")
    verified = verify_claim(claim, evidence)
    assert verified.evidence_type == EvidenceType.NEEDS_VERIFICATION


def test_genuine_evaluation_artifact_upgrades_to_test_evidence():
    test_content = (
        "import pytest\n\n"
        "def test_accuracy_regression():\n"
        "    results = run_evaluation()\n"
        "    assert results['accuracy'] >= 95  # recorded benchmark run\n"
    )
    evidence = sample_evidence(
        test_files=["tests/test_accuracy.py"],
        test_excerpts={"tests/test_accuracy.py": test_content},
        has_tests=True,
    )
    claim = Claim(statement="The model achieves 95% accuracy")
    verified = verify_claim(claim, evidence)
    assert verified.evidence_type == EvidenceType.TEST_EVIDENCE_FOUND
    assert verified.source == "tests/test_accuracy.py"
    assert verified.line_start is not None
    assert "Confirm" in verified.needs_action  # still requires human confirmation


def test_metric_without_number_is_soft_claim():
    evidence = sample_evidence(source_excerpts={})
    verified = verify_claim(Claim(statement="It is significantly faster now"), evidence)
    assert verified.evidence_type == EvidenceType.NEEDS_VERIFICATION


# --- adoption / deployment --------------------------------------------------


def test_fabricated_user_count_is_never_verified_from_code():
    evidence = sample_evidence(
        source_excerpts={"app/main.py": "USERS = 0  # local counter for the demo\n"},
    )
    verified = verify_claim(Claim(statement="We have 50,000 users worldwide"), evidence)
    assert verified.evidence_type == EvidenceType.NEEDS_VERIFICATION
    assert "adoption" in verified.needs_action or "production" in verified.needs_action


def test_team_provided_user_count_is_labelled_not_verified():
    team = TeamContext(impact_claims=["We have 50 users from our pilot"])
    evidence = sample_evidence(source_excerpts={})
    verified = verify_claim(Claim(statement="We have 50 users from our pilot"), evidence, team)
    assert verified.evidence_type == EvidenceType.TEAM_PROVIDED


def test_deployment_claim_from_code_is_flagged():
    evidence = sample_evidence(
        source_excerpts={"deploy.sh": "kubectl apply -f deployment.yaml\n"},
        file_tree=["deploy.sh"],
    )
    verified = verify_claim(Claim(statement="The service is deployed in production"), evidence)
    assert verified.evidence_type == EvidenceType.NEEDS_VERIFICATION


# --- source-cited claims ----------------------------------------------------


def test_source_cited_claim_requires_inspected_file():
    evidence = sample_evidence(
        file_tree=["src/app.py"],
        source_excerpts={"src/app.py": "def start_app():\n    return True"},
    )
    claim = Claim(statement="The repository contains an app entry point", source="src/app.py")
    deck = verify_claims(sample_deck(claim), evidence, TeamContext())
    assert deck.slides[0].claims[0].evidence_type == EvidenceType.REPO_EVIDENCE


def test_uninspected_cited_file_is_flagged():
    evidence = sample_evidence(file_tree=["src/big_module.py"], source_excerpts={})
    verified = verify_claim(
        Claim(statement="Handles authentication with tokens", source="src/big_module.py"),
        evidence,
    )
    assert verified.evidence_type == EvidenceType.NEEDS_VERIFICATION


def test_readme_only_support_is_team_authored():
    evidence = sample_evidence(readme_content="# Demo\nWe process 1 million records per second.\n")
    verified = verify_claim(Claim(statement="We process 1 million records per second"), evidence)
    assert verified.evidence_type == EvidenceType.TEAM_PROVIDED
    assert "README" in verified.needs_action


def test_test_file_citation_yields_test_evidence():
    evidence = sample_evidence(
        test_files=["tests/test_flow.py"],
        test_excerpts={"tests/test_flow.py": "def test_flow():\n    assert run_flow() is True"},
        has_tests=True,
    )
    verified = verify_claim(
        Claim(statement="The main flow is covered by an automated test", source="tests/test_flow.py"),
        evidence,
    )
    assert verified.evidence_type == EvidenceType.TEST_EVIDENCE_FOUND


# --- candidate retrieval ----------------------------------------------------


def test_candidates_require_more_than_single_weak_overlap():
    evidence = sample_evidence(
        source_excerpts={"src/feature.py": "# features live here\nFEATURES = []\n"},
    )
    claim = Claim(statement="Adds neural rendering with adversarial training")
    assert retrieve_candidates(claim.statement, evidence) == []


def test_candidates_record_line_references():
    content = "line one\nneural rendering happens here\nline three"
    evidence = sample_evidence(source_excerpts={"src/render.py": content})
    claim = Claim(statement="The neural rendering pipeline")
    candidates = retrieve_candidates(claim.statement, evidence)
    assert candidates
    assert candidates[0].path == "src/render.py"
    assert candidates[0].line_start == 2


def test_uncited_claim_with_candidates_becomes_repo_evidence():
    content = "def neural_render():\n    return render_neural_frames()"
    evidence = sample_evidence(source_excerpts={"src/render.py": content})
    verified = verify_claim(Claim(statement="Includes a neural rendering pipeline"), evidence)
    assert verified.evidence_type == EvidenceType.REPO_EVIDENCE
    assert verified.source == "src/render.py"


# --- deck-level scrubbing ---------------------------------------------------


def test_unsupported_metric_is_removed_from_export_bullet():
    evidence = sample_evidence(source_excerpts={})
    claim = Claim(statement="The model achieves 95% accuracy", source="src/model.py")
    deck = PitchDeck(
        project_name="Demo", tagline="A demo project",
        slides=[
            SlideContent(slide_number=i, title=f"Slide {i}", bullet_points=["The model achieves 95% accuracy"], claims=[claim])
            for i in range(1, 7)
        ], total_duration_seconds=180,
    )
    deck = verify_claims(deck, evidence, TeamContext())
    assert deck.slides[0].bullet_points[0] == "Metric omitted until the team provides supporting evidence."


def test_bullet_without_claim_record_still_reviewed():
    evidence = sample_evidence(source_excerpts={})
    deck = PitchDeck(
        project_name="Demo", tagline="Demo",
        slides=[SlideContent(slide_number=i, title=f"S{i}", bullet_points=["A fresh unrecorded assertion"]) for i in range(1, 7)],
        total_duration_seconds=180,
    )
    deck = verify_claims(deck, evidence, TeamContext())
    assert all(slide.claims for slide in deck.slides)
    assert deck.unverified_claims
