"""Read-only GitHub repository analysis. Imported code is never executed.

Repository text (READMEs, comments, dependency metadata) is treated strictly
as untrusted data: it is size-bounded, secret-redacted, and never interpreted
as instructions by this module.
"""
from __future__ import annotations

import json
import re
import ast
import time
from pathlib import PurePosixPath
from urllib.parse import urlparse, quote
from typing import Optional

import requests

from config import settings
from hackpack.models import RepoEvidence, TechStackItem


class RepositoryAnalysisError(RuntimeError):
    """Raised when a repository cannot safely be analyzed."""


DEPENDENCY_FILES = {
    "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg",
    "package.json", "cargo.toml", "go.mod", "gemfile", "pom.xml",
    "build.gradle", "build.gradle.kts", "composer.json", "mix.exs",
}
README_NAMES = {"readme.md", "readme.rst", "readme", "readme.txt"}
SKIP_DIRS = {
    "node_modules", "vendor", "dist", "build", "target", "coverage",
    ".git", ".venv", "venv", "__pycache__", ".next", "site-packages",
}
SKIP_FILE_NAMES = {
    "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock",
    "cargo.lock", "composer.lock", "gemfile.lock", "go.sum",
}
SECRET_PATH_PARTS = {"secrets", "credentials", "private", "certs", "certificates"}

# Best-effort redaction before source excerpts are shown or passed to a model.
SECRET_PATTERNS = [
    re.compile(r"(?i)\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b"),
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[A-Za-z0-9._~+/-]+=*"),
    re.compile(r"(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token|password)\s*([=:])\s*(['\"])[^'\"\n]{6,}\3"),
]


def parse_github_url(repo_url: str) -> tuple[str, str]:
    """Validate a standard public GitHub repository URL and return owner/name."""
    try:
        parsed = urlparse(repo_url.strip())
    except Exception as exc:
        raise RepositoryAnalysisError("Enter a valid GitHub repository URL.") from exc
    if parsed.scheme not in {"https", "http"} or parsed.hostname not in {"github.com", "www.github.com"}:
        raise RepositoryAnalysisError("For v0.1, use a repository URL hosted on github.com.")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise RepositoryAnalysisError("Use a URL like https://github.com/owner/repository.")
    owner, name = parts[0], parts[1]
    if name.endswith(".git"):
        name = name[:-4]
    if not owner or not name or owner in {".", ".."} or name in {".", ".."}:
        raise RepositoryAnalysisError("The repository URL does not contain a valid owner and name.")
    return owner, name


def _redact(text: str) -> str:
    clean = text
    for pattern in SECRET_PATTERNS:
        if pattern.pattern.startswith("(?i)(authorization"):
            clean = pattern.sub(r"\1[REDACTED]", clean)
        else:
            clean = pattern.sub("[REDACTED_SECRET]", clean)
    return clean


def _is_skippable(path: str) -> bool:
    p = PurePosixPath(path)
    lowered_parts = {part.lower() for part in p.parts}
    if lowered_parts & SKIP_DIRS or lowered_parts & SECRET_PATH_PARTS:
        return True
    name = p.name.lower()
    if name in SKIP_FILE_NAMES:
        return True
    if name.startswith(".env") and name not in {".env.example", ".env.sample", ".env.template"}:
        return True
    if name.endswith((".pem", ".p12", ".pfx", ".key", ".keystore")):
        return True
    if name in {"id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"}:
        return True
    if "credential" in name or "secret" in name or "private_key" in name:
        return True
    return False


def _priority(path: str) -> tuple[int, int, str]:
    p = path.lower()
    name = PurePosixPath(path).name.lower()
    if name in README_NAMES:
        rank = 0
    elif name in DEPENDENCY_FILES:
        rank = 1
    elif name in {"dockerfile", "docker-compose.yml", "compose.yaml", "makefile", "procfile"}:
        rank = 2
    elif p.startswith(".github/workflows/"):
        rank = 3
    elif name in {"app.py", "main.py", "server.py", "index.js", "index.ts", "main.go", "manage.py"}:
        rank = 4
    elif any(segment in p for segment in ("/src/", "/app/", "/backend/", "/frontend/", "/lib/")):
        rank = 5
    elif "/test" in p or "__tests__" in p:
        rank = 6
    else:
        rank = 7
    return rank, len(path), p


def _raw_download(owner: str, repo_name: str, branch: str, path: str, max_bytes: int) -> Optional[str]:
    branch_path = quote(branch, safe="/")
    file_path = quote(path, safe="/")
    url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch_path}/{file_path}"
    try:
        with requests.get(url, timeout=(5, 15), stream=True, headers={"User-Agent": "HackPack/0.1"}) as response:
            if response.status_code != 200:
                return None
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    return None
                chunks.append(chunk)
            data = b"".join(chunks)
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                return data.decode("utf-8", errors="replace")
    except requests.RequestException:
        return None


def _parse_requirement_name(line: str) -> Optional[str]:
    stripped = line.strip()
    if not stripped or stripped.startswith(("#", "-", "--")):
        return None
    # Basic requirements syntax: package[extra]>=version; hashes/environment markers are ignored.
    match = re.match(r"\s*([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?\s*(?:[<>=!~].*)?$", stripped)
    return match.group(1) if match else None


def _collect_dependencies(path: str, content: str) -> list[TechStackItem]:
    name = PurePosixPath(path).name.lower()
    found: list[TechStackItem] = []

    def add(dep: str, version: Optional[str] = None, category: str = "library") -> None:
        dep = dep.strip()
        if not dep:
            return
        found.append(TechStackItem(name=dep, version=version, category=category, evidence_file=path))

    try:
        if name == "requirements.txt":
            for line in content.splitlines():
                dep = _parse_requirement_name(line)
                if dep:
                    version_match = re.search(r"(?:==|~=|>=|<=|>|<)([A-Za-z0-9.*+_-]+)", line)
                    add(dep, version_match.group(1) if version_match else None)
        elif name == "package.json":
            data = json.loads(content)
            for section in ("dependencies", "devDependencies"):
                for dep, version in (data.get(section) or {}).items():
                    add(dep, str(version), "framework" if dep.lower() in {"react", "next", "vue", "express", "svelte", "angular"} else "library")
        elif name in {"pyproject.toml", "cargo.toml"}:
            try:
                import tomllib
            except ImportError:  # Python 3.10
                import tomli as tomllib  # type: ignore
            data = tomllib.loads(content)
            if name == "pyproject.toml":
                deps = (data.get("project") or {}).get("dependencies") or []
                for dep_line in deps:
                    dep = _parse_requirement_name(dep_line)
                    if dep:
                        add(dep, None, "library")
                poetry_deps = (data.get("tool") or {}).get("poetry", {}).get("dependencies", {})
                for dep, version in poetry_deps.items():
                    if dep.lower() != "python":
                        add(dep, str(version) if isinstance(version, (str, int, float)) else None)
            else:
                for section in (data.get("dependencies") or {}, data.get("dev-dependencies") or {}):
                    for dep, version in section.items():
                        add(dep, str(version) if isinstance(version, str) else None)
        elif name == "go.mod":
            for match in re.finditer(r"(?m)^\s*(?:require\s+)?(\S+)\s+(v\S+)", content):
                add(match.group(1).split("/")[-1], match.group(2), "module")
        elif name in {"build.gradle", "build.gradle.kts"}:
            for match in re.finditer(r"(?m)\b(?:implementation|api|runtimeOnly|testImplementation)\s*\(?\s*['\"]([^:'\"]+):([^:'\"]+):([^'\"]+)", content):
                add(match.group(2), match.group(3), "library")
        elif name == "pom.xml":
            import xml.etree.ElementTree as ET
            root = ET.fromstring(content)
            ns = {"m": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
            prefix = "m:" if ns else ""
            for dep in root.findall(f".//{prefix}dependency", ns):
                artifact = dep.findtext(f"{prefix}artifactId", namespaces=ns)
                version = dep.findtext(f"{prefix}version", namespaces=ns)
                if artifact:
                    add(artifact, version)
    except Exception:
        # Malformed/unusual manifest should not prevent the rest of the repo from being analyzed.
        return found
    return found


def _extract_python_module(path: str, content: str) -> dict:
    item: dict = {"path": path, "purpose": "Python module", "classes": [], "functions": []}
    try:
        tree = ast.parse(content)
        module_doc = ast.get_docstring(tree)
        if module_doc:
            item["purpose"] = module_doc.splitlines()[0][:180]
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                args = [arg.arg for arg in node.args.args[:8]]
                item["functions"].append({"name": node.name, "args": args, "doc": (ast.get_docstring(node) or "")[:180]})
            elif isinstance(node, ast.ClassDef):
                item["classes"].append({"name": node.name, "doc": (ast.get_docstring(node) or "")[:180]})
        item["functions"] = item["functions"][:12]
        item["classes"] = item["classes"][:8]
    except (SyntaxError, ValueError):
        item["purpose"] = "Python file (syntax could not be parsed statically)"
    return item


def _is_test_path(path: str) -> bool:
    p = path.lower()
    return (
        p.startswith(("tests/", "test/")) or "/tests/" in p or "/test/" in p or "__tests__" in p
        or PurePosixPath(p).name.lower().startswith(("test_", "test."))
        or PurePosixPath(p).stem.lower().endswith("_test")
    )


def analyze_repository(
    repo_url: str,
    github_token: Optional[str] = None,
    time_budget_seconds: Optional[int] = None,
) -> RepoEvidence:
    """Analyze a public GitHub repository without executing its source code."""
    owner, name = parse_github_url(repo_url)
    try:
        from github import Github
    except ImportError as exc:
        raise RepositoryAnalysisError("PyGithub is not installed. Run `pip install -r requirements.txt`.") from exc

    token = github_token or settings.GITHUB_TOKEN or None
    client = Github(login_or_token=token) if token else Github()
    warnings: list[str] = []
    deadline = time.monotonic() + (
        settings.ANALYSIS_TIME_BUDGET_SECONDS if time_budget_seconds is None else time_budget_seconds
    )
    try:
        repo = client.get_repo(f"{owner}/{name}")
        branch = repo.default_branch
        tree = repo.get_git_tree(branch, recursive=True)
        if getattr(tree, "truncated", False):
            warnings.append("GitHub returned a truncated file tree; some files may not have been inspected.")
        regular_paths = []
        for node in tree.tree:
            if node.type != "blob" or getattr(node, "mode", "100644") not in {"100644", "100755"}:
                continue
            path = node.path
            if _is_skippable(path):
                continue
            regular_paths.append(path)
        selected = sorted(regular_paths, key=_priority)[: settings.MAX_FILES_TO_ANALYZE]
        # Always try to include a few test files so the verifier can weigh
        # real test code, even when the priority sort would skip them.
        test_paths = [p for p in regular_paths if _is_test_path(p) and not _is_skippable(p)]
        for test_path in sorted(test_paths, key=len)[: settings.MAX_TEST_EXCERPTS]:
            if test_path not in selected:
                selected.append(test_path)
        if len(regular_paths) > settings.MAX_FILES_TO_ANALYZE:
            warnings.append(
                f"Analyzed a bounded subset of files ({settings.MAX_FILES_TO_ANALYZE} of "
                f"{len(regular_paths)} eligible paths)."
            )

        description = repo.description
        primary_language = repo.language
        try:
            languages = repo.get_languages()
        except Exception:
            languages = {primary_language: 1} if primary_language else {}
        # PyGithub versions may include non-integer metadata keys; keep counts only.
        languages = {
            str(key): int(value)
            for key, value in dict(languages or {}).items()
            if isinstance(value, int) and not str(key).startswith("http")
        }
        license_name = None
        try:
            if repo.license:
                license_name = repo.license.spdx_id or repo.license.name
        except Exception:
            pass

        contents: dict[str, str] = {}
        tech_stack: list[TechStackItem] = []
        readme_content: Optional[str] = None
        source_excerpts: dict[str, str] = {}
        test_excerpts: dict[str, str] = {}
        total_excerpt_chars = 0
        key_modules: list[dict] = []
        time_budget_exceeded = False

        for path in selected:
            if time.monotonic() > deadline:
                time_budget_exceeded = True
                break
            lower_name = PurePosixPath(path).name.lower()
            needs_for_stack = lower_name in DEPENDENCY_FILES or lower_name in {"dockerfile", "docker-compose.yml", "compose.yaml"}
            is_readme = lower_name in README_NAMES
            is_test = _is_test_path(path)
            is_source = PurePosixPath(path).suffix.lower() in {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".php", ".rb", ".cs", ".cpp", ".c", ".html", ".sql"}
            if not (needs_for_stack or is_readme or is_source or is_test):
                continue
            text = _raw_download(owner, name, branch, path, settings.MAX_FILE_SIZE_BYTES)
            if text is None:
                continue
            text = _redact(text)
            contents[path] = text
            if is_readme and readme_content is None:
                readme_content = text[:settings.MAX_README_LENGTH]
            if needs_for_stack:
                tech_stack.extend(_collect_dependencies(path, text))
                if lower_name == "dockerfile":
                    for image in re.findall(r"(?im)^\s*FROM\s+([^\s]+)", text):
                        tech_stack.append(TechStackItem(name=image, category="container base image", evidence_file=path))
            if path.endswith(".py") and is_source:
                key_modules.append(_extract_python_module(path, text))
            if is_source and len(source_excerpts) < settings.MAX_SOURCE_EXCERPTS:
                excerpt = text[:8_000]
                if total_excerpt_chars + len(excerpt) <= settings.MAX_TOTAL_EXCERPT_CHARS:
                    source_excerpts[path] = excerpt
                    total_excerpt_chars += len(excerpt)
            if is_test and len(test_excerpts) < settings.MAX_TEST_EXCERPTS:
                test_excerpts[path] = text[:6_000]

        if time_budget_exceeded:
            warnings.append(
                "The analysis time budget was reached; some selected files were not inspected."
            )
        if readme_content is None:
            warnings.append("No readable README file was found. Ask the team to provide a project description.")
        total_files = len(regular_paths)

        all_text = (readme_content or "") + "\n" + "\n".join(contents.values())
        demo_urls = sorted(set(re.findall(r"https?://[^\s)\]>\"']+", all_text)))
        demo_urls = [url.rstrip(".,;") for url in demo_urls if not any(host in url.lower() for host in ("github.com/", "raw.githubusercontent.com/", "shields.io/", "img.shields.io/"))][:20]
        paths_lower = [p.lower() for p in regular_paths]
        test_files = [p for p in regular_paths if _is_test_path(p)]
        has_tests = bool(test_files) or any(
            PurePosixPath(p).name.lower().startswith(("test_", "test."))
            or PurePosixPath(p).stem.lower().endswith("_test")
            for p in paths_lower
        )
        has_ci = any(p.startswith(".github/workflows/") or p.startswith(".circleci/") or p in {".gitlab-ci.yml", "azure-pipelines.yml"} for p in paths_lower)
        has_docker = any(PurePosixPath(p).name.lower() in {"dockerfile", "docker-compose.yml", "compose.yaml", "compose.yml"} for p in paths_lower)
        has_demo = bool(demo_urls) or any(p in {"demo.gif", "demo.mp4", "assets/demo.gif"} for p in paths_lower)
        # De-duplicate dependencies by case-insensitive name + source file.
        unique_stack: dict[tuple[str, str], TechStackItem] = {}
        for item in tech_stack:
            unique_stack[(item.name.lower(), item.evidence_file)] = item

        return RepoEvidence(
            repo_url=f"https://github.com/{owner}/{name}",
            repo_name=name,
            description=description,
            readme_content=readme_content,
            file_tree=sorted(regular_paths)[:300],
            tech_stack=list(unique_stack.values())[:100],
            key_modules=key_modules[:20],
            test_files=sorted(test_files)[:200],
            test_excerpts=test_excerpts,
            has_tests=has_tests,
            has_ci=has_ci,
            has_docker=has_docker,
            has_demo=has_demo,
            demo_urls=demo_urls,
            license=license_name,
            total_files=total_files,
            primary_language=primary_language,
            languages=languages or {},
            source_excerpts=source_excerpts,
            analysis_warnings=warnings,
        )
    except Exception as exc:
        # Avoid leaking upstream exception details or tokens into the UI.
        status = getattr(exc, "status", None)
        if status == 404:
            raise RepositoryAnalysisError("Repository not found or not publicly accessible. Check the URL.") from exc
        if status == 403:
            raise RepositoryAnalysisError("GitHub rate limit or access restriction reached. Add a GitHub token in .env and retry.") from exc
        if isinstance(exc, RepositoryAnalysisError):
            raise
        raise RepositoryAnalysisError(f"Could not analyze this repository ({type(exc).__name__}). Check the URL and connection, then retry.") from exc
    finally:
        try:
            client.close()
        except Exception:
            pass
