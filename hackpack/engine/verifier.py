"""Conservative claim verification against repository evidence.

This is deliberately *not* a keyword search that certifies claims. It performs
targeted candidate retrieval (keywords, metric patterns, metadata), records
where the candidates came from with line references, and then applies strict
classification rules:

* A source file that merely *contains* code related to a feature is not
  evidence that the feature works end to end.
* Numerical results require the value, the metric name, and a test/evaluation
  context in inspected content. A stray ``95%`` anywhere in the repository does
  NOT verify "95% accuracy".
* README-only support is treated as a team-authored statement, not proof.
* Deployment, production usage, user adoption, benchmark results and business
  impact are never inferred from the existence of code.

Every ambiguous claim is flagged for human review. False verification is
considered worse than asking for confirmation.
"""
from __future__ import annotations

import re
from hackpack.models import (
    Claim,
    ClaimCategory,
    EvidenceCandidate,
    EvidenceType,
    PitchDeck,
    RepoEvidence,
    TeamContext,
)

# Heuristic vocabulary for claim categorisation and candidate retrieval.
_METRIC_WORDS = re.compile(
    r"(?i)\b(accuracy|precision|recall|f1|latency|throughput|performance|benchmark|"
    r"score|speedup|faster|reduction|increase|improve\w*|success rate|error rate)\b"
)
_ADOPTION_WORDS = re.compile(
    r"(?i)\b(users?|customers?|downloads?|signups?|revenue|clients?|adoption|"
    r"production|deployed|deployment|live|market|business impact|customers)\b"
)
_TECH_WORDS = re.compile(
    r"(?i)\b(built with|uses?|using|powered by|framework|library|libraries|stack|language)\b"
)
_NUMBER_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?%?")

_WORD = re.compile(r"[a-z][a-z0-9_\-]{2,}")
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "has",
    "have", "had", "you", "your", "our", "their", "can", "could", "would", "should",
    "will", "shall", "into", "over", "under", "about", "been", "being", "does", "did",
    "not", "but", "its", "it's", "who", "whom", "what", "when", "where", "how", "why",
    "all", "any", "some", "more", "most", "other", "than", "then", "them", "they",
    "these", "those", "there", "here", "each", "such", "only", "also", "just", "like",
    "allow", "allows", "letting", "users", "via", "per", "one", "two", "new", "using",
    "use", "used", "based", "supports", "support", "provide", "provides", "includes",
    "include", "included", "enable", "enables", "makes", "make", "built", "build",
    "runs", "run", "running", "works", "work", "working", "shows", "show", "give",
    "gives", "helps", "help", "easy", "fast", "fully", "automatically", "project",
    "app", "application", "system", "tool", "pitch", "hackathon", "team", "we",
}

_EVAL_PATH_HINTS = ("test", "eval", "bench", "result", "metrics", "experiment", "accuracy")
_SOURCE_EXCERPT_LIMIT = 8


def categorize_claim(statement: str) -> ClaimCategory:
    """Best-effort claim type. Deterministic and domain independent."""
    text = statement.lower()
    has_number = bool(_NUMBER_TOKEN.search(text))
    if _ADOPTION_WORDS.search(text):
        return ClaimCategory.USER_COUNT if has_number else ClaimCategory.DEPLOYMENT
    if _METRIC_WORDS.search(text) or "%" in text:
        if any(word in text for word in ("latency", "throughput", "faster", "speedup", "performance", "ms", "requests/s")):
            return ClaimCategory.PERFORMANCE
        return ClaimCategory.NUMERICAL_METRIC
    if _TECH_WORDS.search(text):
        return ClaimCategory.TECHNOLOGY
    return ClaimCategory.IMPLEMENTATION


def _keywords(statement: str) -> list[str]:
    words = [w for w in _WORD.findall(statement.lower()) if w not in _STOPWORDS and len(w) >= 4]
    # Preserve order, drop duplicates.
    return list(dict.fromkeys(words))[:12]


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _search_file(path: str, content: str, keywords: list[str]) -> tuple[int, EvidenceCandidate | None]:
    """Return (hit_count, best candidate) for one inspected file."""
    best: tuple[int, EvidenceCandidate] | None = None
    total_hits = 0
    for keyword in keywords:
        pattern = re.compile(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", re.IGNORECASE)
        for match in pattern.finditer(content):
            total_hits += 1
            line = _line_of(content, match.start())
            snippet = content[max(0, match.start() - 120): match.end() + 160]
            snippet = " ".join(snippet.split())[:300]
            candidate = EvidenceCandidate(
                path=path,
                excerpt=snippet,
                line_start=line,
                line_end=line,
                note=f"contains '{keyword}'",
            )
            if best is None:
                best = (1, candidate)
    if best is None:
        return 0, None
    return total_hits, best[1]


def retrieve_candidates(statement: str, evidence: RepoEvidence) -> list[EvidenceCandidate]:
    """Deterministic candidate retrieval with line references.

    A file only becomes a candidate when at least two claim keywords match it
    (or one match of a longer keyword, len >= 6), which avoids certifying
    claims from incidental single-word overlap.
    """
    keywords = _keywords(statement)
    if not keywords:
        return []
    sources: list[tuple[str, str]] = []
    sources.extend(evidence.source_excerpts.items())
    sources.extend(evidence.test_excerpts.items())
    if evidence.readme_content:
        sources.append(("README.md", evidence.readme_content))

    scored: list[tuple[int, EvidenceCandidate]] = []
    for path, content in sources:
        hits, candidate = _search_file(path, content, keywords)
        if candidate is None:
            continue
        strong_single = any(
            len(kw) >= 6 and re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", content, re.IGNORECASE)
            for kw in keywords
        )
        if hits >= 2 or (hits >= 1 and strong_single):
            scored.append((hits, candidate))
    scored.sort(key=lambda pair: (-pair[0], pair[1].path))
    return [candidate for _, candidate in scored[:_SOURCE_EXCERPT_LIMIT]]


def _is_test_or_eval_path(path: str) -> bool:
    lowered = path.lower()
    return any(hint in lowered for hint in _EVAL_PATH_HINTS)


def _find_number_contexts(number: str, evidence: RepoEvidence) -> list[tuple[str, str, int]]:
    """Locate ``(path, surrounding_text, line)`` for a numeric token in inspected content."""
    pattern = re.compile(rf"(?<![\d.]){re.escape(number)}(?![\d.])")
    contexts: list[tuple[str, str, int]] = []
    sources = list(evidence.test_excerpts.items()) + list(evidence.source_excerpts.items())
    if evidence.readme_content:
        sources.append(("README.md", evidence.readme_content))
    for path, content in sources:
        for match in pattern.finditer(content):
            window = content[max(0, match.start() - 160): match.end() + 160]
            contexts.append((path, window, _line_of(content, match.start())))
            break  # one hit per file is enough
    return contexts


def _verify_metric_claim(claim: Claim, evidence: RepoEvidence) -> None:
    """Numerical claims need value + metric name + test/eval context to pass."""
    statement = claim.statement
    metric_match = _METRIC_WORDS.search(statement)
    metric_name = metric_match.group(0).lower() if metric_match else None

    for token in _NUMBER_TOKEN.findall(statement):
        bare = token.rstrip("%").replace(",", "")
        contexts = _find_number_contexts(bare, evidence)
        for path, window, line in contexts:
            window_has_metric = bool(metric_name and metric_name in window.lower())
            if window_has_metric and _is_test_or_eval_path(path):
                claim.evidence_type = EvidenceType.TEST_EVIDENCE_FOUND
                claim.confidence = min(max(claim.confidence, 0.55), 0.75)
                claim.source = path
                claim.line_start = claim.line_end = line
                claim.needs_action = (
                    "A relevant test/evaluation artifact mentions this result. Confirm the "
                    "recorded output is current before presenting it as measured."
                )
                return
        # The number exists somewhere (or not); it never reached the strict bar.
        claim.evidence_type = EvidenceType.NEEDS_VERIFICATION
        claim.confidence = min(claim.confidence, 0.25)
        claim.needs_action = (
            "No inspected test or evaluation artifact records this result with its metric "
            "name. Provide the benchmark/test output or remove the number."
        )
        return

    # A metric-flavoured statement without any number is still a soft claim.
    claim.evidence_type = EvidenceType.NEEDS_VERIFICATION
    claim.confidence = min(claim.confidence, 0.35)
    claim.needs_action = "Describe how this was measured, or present it as a goal rather than a result."


def _team_phrases(team: TeamContext) -> list[str]:
    return [
        team.problem_statement, team.target_users, team.key_results or "",
        team.future_plans or "", *team.impact_claims,
    ]


def _matches_team_context(statement: str, team: TeamContext) -> bool:
    lowered = statement.lower()
    return any(
        phrase and len(phrase.strip()) > 8 and phrase.strip().lower() in lowered
        for phrase in _team_phrases(team)
    )


def verify_claim(claim: Claim, evidence: RepoEvidence, team: TeamContext | None = None) -> Claim:
    """Classify a single claim conservatively and attach retrieval candidates."""
    team = team or TeamContext()
    statement = claim.statement.strip()
    claim.category = categorize_claim(statement)
    claim.candidates = retrieve_candidates(statement, evidence)
    source = (claim.source or "").strip()

    # 1) Adoption, production, deployment and business impact are never proven
    #    by repository code. At best they are team statements.
    if claim.category in {ClaimCategory.USER_COUNT, ClaimCategory.DEPLOYMENT}:
        if _matches_team_context(statement, team) or source.lower().startswith("team"):
            claim.evidence_type = EvidenceType.TEAM_PROVIDED
            claim.confidence = min(claim.confidence, 0.6)
            claim.needs_action = (
                "Team-provided statement. Confirm the team can defend this to judges; "
                "repository code cannot prove adoption or deployment."
            )
        else:
            claim.evidence_type = EvidenceType.NEEDS_VERIFICATION
            claim.confidence = min(claim.confidence, 0.2)
            claim.needs_action = (
                "Code existence does not prove deployment, production usage or adoption. "
                "Provide evidence or rephrase as a plan."
            )
        return claim

    # 2) Numerical and performance claims require test/evaluation context.
    if claim.category in {ClaimCategory.NUMERICAL_METRIC, ClaimCategory.PERFORMANCE} or "%" in statement:
        # A claim explicitly sourced to team results stays a team statement
        # unless test evidence upgrades it.
        if _matches_team_context(statement, team) and not _NUMBER_TOKEN.search(
            " ".join(team.impact_claims)
        ):
            pass  # still subject to the strict metric check below
        _verify_metric_claim(claim, evidence)
        if claim.evidence_type == EvidenceType.NEEDS_VERIFICATION and _matches_team_context(statement, team):
            claim.needs_action = (claim.needs_action or "") + " Marked as team-provided; confirm the source of this figure."
        return claim

    # 3) Explicitly cited source file.
    if source and source in evidence.source_excerpts:
        claim.evidence_type = EvidenceType.REPO_EVIDENCE
        claim.confidence = min(max(claim.confidence, 0.6), 0.85)
        claim.needs_action = (
            "Related code exists in this file. A file's existence does not prove the "
            "feature works end to end; be ready to demo it."
        )
        return claim
    if source and source in evidence.test_excerpts:
        claim.evidence_type = EvidenceType.TEST_EVIDENCE_FOUND
        claim.confidence = min(max(claim.confidence, 0.55), 0.75)
        claim.needs_action = "Relevant test code exists. Confirm the test currently passes."
        return claim
    if source and source in evidence.file_tree:
        claim.evidence_type = EvidenceType.NEEDS_VERIFICATION
        claim.confidence = min(claim.confidence, 0.4)
        claim.needs_action = "This source file was not inspected. Confirm the statement or cite an inspected file."
        return claim
    if source and source.lower() in {"readme.md", "readme", "readme.rst"}:
        # README text is team-authored narrative: a statement, not verification.
        claim.evidence_type = EvidenceType.TEAM_PROVIDED
        claim.confidence = min(claim.confidence, 0.55)
        claim.needs_action = "Supported by the README only, which the team authors. Confirm against the code."
        return claim
    if source and source.lower().startswith("team"):
        claim.evidence_type = EvidenceType.TEAM_PROVIDED
        claim.confidence = min(claim.confidence, 0.65)
        claim.needs_action = "Team-provided statement; confirm it reflects the actual project."
        return claim

    # 4) No explicit source: use retrieved candidates, conservatively.
    best_path = claim.candidates[0].path if claim.candidates else None
    if best_path and best_path != "README.md":
        claim.evidence_type = EvidenceType.REPO_EVIDENCE
        claim.source = best_path
        if claim.candidates[0].line_start:
            claim.line_start = claim.candidates[0].line_start
            claim.line_end = claim.candidates[0].line_end
        claim.confidence = min(max(claim.confidence, 0.55), 0.75)
        claim.needs_action = (
            "Matched against inspected source; confirm this reflects the behaviour you will present."
        )
        return claim

    if _matches_team_context(statement, team):
        claim.evidence_type = EvidenceType.TEAM_PROVIDED
        claim.confidence = min(claim.confidence, 0.6)
        claim.needs_action = claim.needs_action or (
            "Team-provided statement; confirm it reflects the actual project and can be defended to judges."
        )
        return claim

    if best_path == "README.md":
        claim.evidence_type = EvidenceType.TEAM_PROVIDED
        claim.confidence = min(claim.confidence, 0.5)
        claim.source = "README.md"
        claim.needs_action = "Supported by the README only, which the team authors. Confirm against the code."
        return claim

    claim.evidence_type = EvidenceType.NEEDS_VERIFICATION
    claim.confidence = min(claim.confidence, 0.3)
    claim.needs_action = claim.needs_action or "Add a valid source, confirm this with the team, or remove the claim."
    return claim


def _bullet_matches_claim(bullet: str, claim: Claim) -> bool:
    bullet_norm = " ".join(bullet.lower().split())
    claim_norm = " ".join(claim.statement.lower().split())
    return bool(bullet_norm and claim_norm and (bullet_norm in claim_norm or claim_norm in bullet_norm))


def verify_claims(pitch: PitchDeck, evidence: RepoEvidence, team: TeamContext | None = None) -> PitchDeck:
    """Classify every displayed bullet/claim and block unsupported metrics from the deck."""
    team = team or TeamContext()
    unverified: list[Claim] = []
    seen: set[tuple[str, str | None]] = set()

    def _record(claim: Claim) -> None:
        if claim.evidence_type in {EvidenceType.NEEDS_VERIFICATION, EvidenceType.INFERRED} or claim.needs_action:
            key = (claim.statement, claim.source)
            if key not in seen:
                unverified.append(claim.model_copy(deep=True))
                seen.add(key)

    for slide in pitch.slides:
        # Ensure slide bullets get reviewed even when the model omitted claim records.
        for bullet in slide.bullet_points:
            if not any(_bullet_matches_claim(bullet, claim) for claim in slide.claims):
                slide.claims.append(
                    Claim(statement=bullet, evidence_type=EvidenceType.INFERRED, source=None, confidence=0.3)
                )

        for claim in slide.claims:
            verify_claim(claim, evidence, team)
            _record(claim)

        # Unsupported numerical claims never export as proven facts.
        replaced_bullets: list[str] = []
        for bullet in slide.bullet_points:
            matching = next((c for c in slide.claims if _bullet_matches_claim(bullet, c)), None)
            unsupported_metric = (
                matching is not None
                and matching.evidence_type in {EvidenceType.NEEDS_VERIFICATION, EvidenceType.INFERRED}
                and matching.category in {ClaimCategory.NUMERICAL_METRIC, ClaimCategory.PERFORMANCE, ClaimCategory.USER_COUNT}
            )
            if unsupported_metric:
                replaced_bullets.append("Metric omitted until the team provides supporting evidence.")
            else:
                replaced_bullets.append(bullet)
        slide.bullet_points = replaced_bullets

        notes_claim = Claim(
            statement=(slide.speaker_notes.strip() or slide.title)[:400],
            evidence_type=EvidenceType.INFERRED,
            source=None,
            confidence=0.3,
        )
        notes_claim = verify_claim(notes_claim, evidence, team)
        notes_metric = notes_claim.category in {
            ClaimCategory.NUMERICAL_METRIC, ClaimCategory.PERFORMANCE, ClaimCategory.USER_COUNT,
        }
        if notes_metric and notes_claim.evidence_type == EvidenceType.NEEDS_VERIFICATION:
            notes_claim.needs_action = (
                "The speaker notes contain a numerical/metric claim without matching evidence. "
                "Add test results or remove the number."
            )
            _record(notes_claim)
            slide.speaker_notes = (
                "Explain the implementation and current limitations. Do not state a numerical "
                "result unless the team can show the corresponding test output or benchmark evidence."
            )

    pitch.unverified_claims = unverified
    return pitch
