from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from app.schemas.code import DEFAULT_CODE_EXCLUDE_GLOBS, DEFAULT_CODE_INCLUDE_GLOBS
from app.services.code_parser import detect_language


class CodeRepositoryLoaderError(RuntimeError):
    """Raised when a Git repository cannot be loaded."""


@dataclass(frozen=True)
class ClonedRepository:
    repo_url: str
    repo_name: str
    branch: str
    commit_sha: str
    path: Path
    storage_path: str
    already_present: bool = False


@dataclass(frozen=True)
class CodeFileDiscovery:
    paths: list[Path]
    skipped_files: int
    skip_reasons: dict[str, int]


class GitRepositoryLoader:
    def __init__(
        self,
        repositories_dir: str | Path,
        allowed_hosts: list[str] | None = None,
    ) -> None:
        self.repositories_dir = Path(repositories_dir)
        self.allowed_hosts = [host.casefold() for host in (allowed_hosts or ["*"])]

    def clone_repository(self, repo_url: str, branch: str) -> ClonedRepository:
        normalized_repo_url = repo_url.strip()
        normalized_branch = branch.strip()
        if not normalized_repo_url:
            raise CodeRepositoryLoaderError("Repository URL is required.")
        if not normalized_branch:
            raise CodeRepositoryLoaderError("Repository branch is required.")

        self._validate_allowed_repository_host(normalized_repo_url)
        repo_name = _safe_repo_name(normalized_repo_url)
        temp_path = self.repositories_dir / "_tmp" / f"{repo_name}-{uuid4().hex}"
        try:
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            _run_git(
                [
                    "clone",
                    "--depth",
                    "1",
                    "--branch",
                    normalized_branch,
                    normalized_repo_url,
                    str(temp_path),
                ],
                cwd=None,
            )
            commit_sha = _run_git(["rev-parse", "HEAD"], cwd=temp_path).strip()
            final_path = self.repositories_dir / repo_name / normalized_branch / commit_sha
            storage_path = final_path.relative_to(self.repositories_dir).as_posix()
            if final_path.exists():
                shutil.rmtree(temp_path, ignore_errors=True)
                return ClonedRepository(
                    repo_url=normalized_repo_url,
                    repo_name=repo_name,
                    branch=normalized_branch,
                    commit_sha=commit_sha,
                    path=final_path,
                    storage_path=storage_path,
                    already_present=True,
                )

            final_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(temp_path), str(final_path))
            return ClonedRepository(
                repo_url=normalized_repo_url,
                repo_name=repo_name,
                branch=normalized_branch,
                commit_sha=commit_sha,
                path=final_path,
                storage_path=storage_path,
            )
        except CodeRepositoryLoaderError:
            shutil.rmtree(temp_path, ignore_errors=True)
            raise
        except OSError as exc:
            shutil.rmtree(temp_path, ignore_errors=True)
            raise CodeRepositoryLoaderError(
                f"Failed to store cloned repository '{normalized_repo_url}': {exc}"
            ) from exc

    def discover_code_files(
        self,
        repository_path: Path,
        include_globs: list[str] | None = None,
        exclude_globs: list[str] | None = None,
        max_file_bytes: int = 1_000_000,
    ) -> list[Path]:
        return self.discover_code_files_with_stats(
            repository_path=repository_path,
            include_globs=include_globs,
            exclude_globs=exclude_globs,
            max_file_bytes=max_file_bytes,
        ).paths

    def discover_code_files_with_stats(
        self,
        repository_path: Path,
        include_globs: list[str] | None = None,
        exclude_globs: list[str] | None = None,
        max_file_bytes: int = 1_000_000,
    ) -> CodeFileDiscovery:
        include_globs = include_globs or DEFAULT_CODE_INCLUDE_GLOBS
        exclude_globs = [*DEFAULT_CODE_EXCLUDE_GLOBS, *(exclude_globs or [])]
        include_spec = _build_pathspec(include_globs)
        exclude_spec = _build_pathspec([*exclude_globs, *_read_gitignore(repository_path)])

        discovered_files: list[Path] = []
        skip_reasons: dict[str, int] = {}
        for path in sorted(repository_path.rglob("*")):
            if not path.is_file() or ".git" in path.parts:
                continue

            relative_path = path.relative_to(repository_path).as_posix()
            if exclude_spec.match_file(relative_path):
                _count_skip(skip_reasons, "excluded_path")
                continue
            if not include_spec.match_file(relative_path):
                _count_skip(skip_reasons, "unsupported_extension")
                continue
            if detect_language(path) is None:
                _count_skip(skip_reasons, "unsupported_extension")
                continue
            try:
                if path.stat().st_size > max_file_bytes:
                    _count_skip(skip_reasons, "too_large")
                    continue
            except OSError:
                _count_skip(skip_reasons, "stat_error")
                continue

            discovered_files.append(path)

        return CodeFileDiscovery(
            paths=discovered_files,
            skipped_files=sum(skip_reasons.values()),
            skip_reasons=skip_reasons,
        )

    def _validate_allowed_repository_host(self, repo_url: str) -> None:
        if "*" in self.allowed_hosts:
            return

        parsed_url = urlparse(repo_url)
        host = (parsed_url.hostname or "").casefold()
        if not host or host not in self.allowed_hosts:
            allowed_hosts = ", ".join(sorted(self.allowed_hosts))
            raise CodeRepositoryLoaderError(
                f"Repository host is not allowed. Allowed hosts: {allowed_hosts}"
            )


class CodeRepositoryAlreadyIndexedError(CodeRepositoryLoaderError):
    """Raised when a cloned repository revision already exists on disk."""


def cleanup_repository(repository: ClonedRepository) -> None:
    if repository.already_present:
        return

    shutil.rmtree(repository.path, ignore_errors=True)


def _run_git(args: list[str], cwd: Path | None) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd is not None else None,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise CodeRepositoryLoaderError("Git CLI is not installed.") from exc
    except subprocess.TimeoutExpired as exc:
        raise CodeRepositoryLoaderError("Git command timed out.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise CodeRepositoryLoaderError(
            f"Git command failed: {' '.join(args)}. {stderr}"
        ) from exc

    return completed.stdout


def _safe_repo_name(repo_url: str) -> str:
    raw_name = repo_url.rstrip("/").rsplit("/", 1)[-1]
    if raw_name.endswith(".git"):
        raw_name = raw_name[:-4]

    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", raw_name).strip("._-")
    if not safe_name:
        raise CodeRepositoryLoaderError("Repository name could not be resolved.")

    return safe_name[:120]


def _count_skip(skip_reasons: dict[str, int], reason: str) -> None:
    skip_reasons[reason] = skip_reasons.get(reason, 0) + 1


def _build_pathspec(patterns: list[str]):
    try:
        import pathspec
    except ImportError as exc:
        raise CodeRepositoryLoaderError(
            "Code repository file matching requires pathspec. "
            "Install dependencies with `pip install -r requirements.txt`."
        ) from exc

    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def _read_gitignore(repository_path: Path) -> list[str]:
    gitignore_path = repository_path / ".gitignore"
    try:
        return gitignore_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    except UnicodeDecodeError:
        return []
    except OSError:
        return []
