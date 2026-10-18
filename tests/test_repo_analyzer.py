"""Repository analyzer tests. Network access is mocked; no token required."""
import pytest

from hackpack.engine.repo_analyzer import (
    RepositoryAnalysisError,
    _collect_dependencies,
    _is_skippable,
    _is_test_path,
    _parse_requirement_name,
    _redact,
    analyze_repository,
    parse_github_url,
)


# --- URL validation ---------------------------------------------------------


def test_parse_github_url():
    assert parse_github_url("https://github.com/openai/example.git") == ("openai", "example")
    assert parse_github_url("https://www.github.com/owner/repo") == ("owner", "repo")
    assert parse_github_url("  https://github.com/owner/repo  ") == ("owner", "repo")


def test_rejects_non_github_hosts():
    with pytest.raises(RepositoryAnalysisError):
        parse_github_url("https://github.com.evil.example/owner/repo")
    with pytest.raises(RepositoryAnalysisError):
        parse_github_url("https://gitlab.com/owner/repo")
    with pytest.raises(RepositoryAnalysisError):
        parse_github_url("http://169.254.169.254/owner/repo")


def test_rejects_urls_without_owner_and_repo():
    with pytest.raises(RepositoryAnalysisError):
        parse_github_url("https://github.com/owner")
    with pytest.raises(RepositoryAnalysisError):
        parse_github_url("https://github.com/")


def test_rejects_empty_and_malformed_urls():
    with pytest.raises(RepositoryAnalysisError):
        parse_github_url("not a url at all")


# --- dependency parsing -----------------------------------------------------


def test_requirement_parser():
    assert _parse_requirement_name("requests>=2.0") == "requests"
    assert _parse_requirement_name("# comment") is None
    assert _parse_requirement_name("--index-url https://example.invalid") is None


def test_collect_dependencies_requirements_txt():
    content = "requests==2.32.0\npydantic>=2.7\n# comment\nfastapi[all]>=0.111\n"
    items = _collect_dependencies("requirements.txt", content)
    names = {item.name for item in items}
    assert {"requests", "pydantic", "fastapi"} <= names
    assert next(i for i in items if i.name == "requests").version == "2.32.0"


def test_collect_dependencies_package_json():
    content = '{"dependencies": {"react": "^18.0.0", "express": "4.18.2"}, "devDependencies": {"jest": "^29.0.0"}}'
    items = _collect_dependencies("package.json", content)
    by_name = {item.name: item for item in items}
    assert by_name["react"].category == "framework"
    assert by_name["jest"].category == "library"


def test_collect_dependencies_pyproject_toml():
    content = """
[project]
dependencies = ["fastapi>=0.111", "uvicorn>=0.30"]
"""
    items = _collect_dependencies("pyproject.toml", content)
    assert {"fastapi", "uvicorn"} <= {item.name for item in items}


def test_collect_dependencies_cargo_toml():
    content = '[dependencies]\nserde = "1.0"\ntokio = { version = "1.35", features = ["full"] }\n'
    items = _collect_dependencies("Cargo.toml", content)
    assert {"serde", "tokio"} <= {item.name for item in items}


def test_collect_dependencies_go_mod():
    content = "module example.com/demo\n\ngo 1.22\n\nrequire github.com/gin-gonic/gin v1.9.1\n"
    items = _collect_dependencies("go.mod", content)
    assert any("gin" in item.name for item in items)


def test_malformed_manifest_does_not_crash():
    assert _collect_dependencies("package.json", "{ not valid json") == []
    assert _collect_dependencies("pyproject.toml", "not [valid toml") == []


# --- exclusions and redaction ----------------------------------------------


def test_secret_files_are_skipped():
    assert _is_skippable(".env")
    assert _is_skippable("config/.env.production")
    assert _is_skippable("private/credentials.json")
    assert _is_skippable("id_rsa")
    assert _is_skippable("certs/server.pem")
    assert _is_skippable("node_modules/react/index.js")
    assert _is_skippable("package-lock.json")
    assert not _is_skippable(".env.example")
    assert not _is_skippable("src/main.py")


def test_test_path_detection():
    assert _is_test_path("tests/test_api.py")
    assert _is_test_path("src/__tests__/component.test.js")
    assert _is_test_path("pkg/utils_test.go")
    assert not _is_test_path("src/latest_feature.py")


def test_redaction_masks_common_secrets():
    text = "token = ghp_ABCDEFGHIJKLMNOPQRST123456 and key sk-abcdefghijklmnop123456"
    cleaned = _redact(text)
    assert "ghp_ABCDEFGHIJKLMNOPQRST123456" not in cleaned
    assert "sk-abcdefghijklmnop123456" not in cleaned
    assert "[REDACTED" in cleaned


# --- full analysis with mocked network -------------------------------------


class FakeNode:
    def __init__(self, path, type_="blob", mode="100644"):
        self.path = path
        self.type = type_
        self.mode = mode


class FakeTree:
    def __init__(self, paths, truncated=False):
        self.tree = [FakeNode(p) for p in paths]
        self.truncated = truncated


class FakeLicense:
    spdx_id = "MIT"
    name = "MIT License"


class FakeRepo:
    default_branch = "main"
    description = "A synthetic demo repository"
    language = "Python"
    license = FakeLicense()

    def __init__(self, paths):
        self._paths = paths

    def get_git_tree(self, branch, recursive=True):
        return FakeTree(self._paths)

    def get_languages(self):
        # Includes a non-integer metadata key, as real PyGithub payloads can.
        return {"Python": 9000, "Shell": 200, "url": "https://api.github.com/repos/acme/demo/language"}


class FakeGithub:
    def __init__(self, paths, exc=None):
        self._paths = paths
        self._exc = exc
        self.closed = False

    def __call__(self, *args, **kwargs):
        return self

    def get_repo(self, full_name):
        if self._exc:
            raise self._exc
        return FakeRepo(self._paths)

    def close(self):
        self.closed = True


FAKE_FILES = {
    "README.md": "# Demo\n\nA synthetic project for tests.\n",
    "requirements.txt": "requests==2.32.0\nfastapi>=0.111\n",
    "app/main.py": "def main():\n    return 'app'\n",
    "tests/test_main.py": "def test_main():\n    assert True\n",
    ".env": "SECRET_KEY=abc123\n",
    "node_modules/react/index.js": "module.exports = {}\n",
    "package-lock.json": '{"lockfileVersion": 3}\n',
}


def install_fakes(monkeypatch, paths=None, exc=None, files=None, download_delay=None):
    import github
    import hackpack.engine.repo_analyzer as ra

    fake = FakeGithub(paths or list(FAKE_FILES.keys()), exc=exc)
    monkeypatch.setattr(github, "Github", fake)

    content = files if files is not None else FAKE_FILES

    def fake_download(owner, repo, branch, path, max_bytes):
        return content.get(path)

    monkeypatch.setattr(ra, "_raw_download", fake_download)
    return fake


def test_analyze_repository_mocked(monkeypatch):
    fake = install_fakes(monkeypatch)
    evidence = analyze_repository("https://github.com/acme/demo")
    assert evidence.repo_url == "https://github.com/acme/demo"
    assert evidence.license == "MIT"
    assert evidence.has_tests is True
    assert "tests/test_main.py" in evidence.test_files
    assert "tests/test_main.py" in evidence.test_excerpts
    assert evidence.has_ci is False
    assert evidence.languages["Python"] == 9000
    assert "url" not in evidence.languages  # metadata keys are dropped
    assert "requests" in {item.name for item in evidence.tech_stack}
    # Secret-bearing and generated files never appear.
    assert all("node_modules" not in p for p in evidence.file_tree)
    assert all(not p.endswith("package-lock.json") for p in evidence.file_tree)
    assert ".env" not in evidence.source_excerpts
    assert fake.closed is True


def test_analyze_repository_detects_ci_and_docker(monkeypatch):
    files = {
        "README.md": "# Demo\n",
        ".github/workflows/ci.yml": "on: push\n",
        "Dockerfile": "FROM python:3.11-slim\n",
        "src/app.py": "print('hi')\n",
    }
    install_fakes(monkeypatch, paths=list(files), files=files)
    evidence = analyze_repository("https://github.com/acme/demo")
    assert evidence.has_ci is True
    assert evidence.has_docker is True
    assert any(item.name.startswith("python:") for item in evidence.tech_stack)


def test_analyze_repository_missing_readme_warns(monkeypatch):
    files = {"src/app.py": "print('hi')\n"}
    install_fakes(monkeypatch, paths=list(files), files=files)
    evidence = analyze_repository("https://github.com/acme/demo")
    assert evidence.readme_content is None
    assert any("README" in warning for warning in evidence.analysis_warnings)


def test_analyze_repository_time_budget(monkeypatch):
    install_fakes(monkeypatch)
    evidence = analyze_repository("https://github.com/acme/demo", time_budget_seconds=0)
    assert any("time budget" in warning for warning in evidence.analysis_warnings)


def test_analyze_repository_not_found(monkeypatch):
    class NotFound(Exception):
        status = 404

    install_fakes(monkeypatch, exc=NotFound())
    with pytest.raises(RepositoryAnalysisError, match="not found"):
        analyze_repository("https://github.com/acme/missing")


def test_analyze_repository_rate_limited(monkeypatch):
    class RateLimited(Exception):
        status = 403

    install_fakes(monkeypatch, exc=RateLimited())
    with pytest.raises(RepositoryAnalysisError, match="rate limit"):
        analyze_repository("https://github.com/acme/demo")
