"""Small helpers for a portable evidence review/export."""
from hackpack.models import RepoEvidence


def summarize_evidence(evidence: RepoEvidence) -> dict:
    return {
        "repository": evidence.repo_url,
        "name": evidence.repo_name,
        "primary_language": evidence.primary_language,
        "languages": evidence.languages,
        "technologies": [item.model_dump() for item in evidence.tech_stack],
        "key_modules": evidence.key_modules,
        "test_files": evidence.test_files[:50],
        "tests_detected": evidence.has_tests,
        "ci_detected": evidence.has_ci,
        "docker_detected": evidence.has_docker,
        "demo_urls": evidence.demo_urls,
        "total_files": evidence.total_files,
        "warnings": evidence.analysis_warnings,
    }
