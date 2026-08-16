import subprocess

from app.services.code_repository_loader import GitRepositoryLoader


def test_git_repository_loader_clones_and_discovers_code_files(tmp_path) -> None:
    source_repo = tmp_path / "source-repo"
    source_repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=source_repo, check=True)
    (source_repo / "app.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
    (source_repo / "Controller.php").write_text(
        "<?php\nclass Controller {}\n",
        encoding="utf-8",
    )
    (source_repo / "README.md").write_text("# Ignore\n", encoding="utf-8")
    (source_repo / "logo.png").write_bytes(b"not source")
    (source_repo / "vendor").mkdir()
    (source_repo / "vendor" / "Ignored.php").write_text(
        "<?php\nclass Ignored {}\n",
        encoding="utf-8",
    )
    (source_repo / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (source_repo / "ignored.py").write_text("def hidden():\n    pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=source_repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test User",
            "commit",
            "-m",
            "initial",
        ],
        cwd=source_repo,
        check=True,
    )

    loader = GitRepositoryLoader(repositories_dir=tmp_path / "repositories")
    cloned = loader.clone_repository(repo_url=str(source_repo), branch="main")
    discovery = loader.discover_code_files_with_stats(
        repository_path=cloned.path,
        include_globs=None,
        exclude_globs=None,
    )
    files = discovery.paths

    assert cloned.repo_name == "source-repo"
    assert cloned.branch == "main"
    assert len(cloned.commit_sha) == 40
    assert {path.relative_to(cloned.path).as_posix() for path in files} == {
        "Controller.php",
        "README.md",
        "app.py",
    }
    assert discovery.skip_reasons["excluded_path"] >= 1
    assert discovery.skip_reasons["unsupported_extension"] >= 1

    repeated = loader.clone_repository(repo_url=str(source_repo), branch="main")

    assert repeated.path == cloned.path
    assert repeated.commit_sha == cloned.commit_sha
    assert repeated.already_present is True
