import subprocess

from app.services.code_repository_loader import GitRepositoryLoader


def test_git_repository_loader_clones_and_discovers_code_files(tmp_path) -> None:
    source_repo = tmp_path / "source-repo"
    source_repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=source_repo, check=True)
    (source_repo / "app.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
    (source_repo / "README.md").write_text("# Ignore\n", encoding="utf-8")
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
    files = loader.discover_code_files(
        repository_path=cloned.path,
        include_globs=["**/*.py"],
        exclude_globs=[],
    )

    assert cloned.repo_name == "source-repo"
    assert cloned.branch == "main"
    assert len(cloned.commit_sha) == 40
    assert [path.relative_to(cloned.path).as_posix() for path in files] == ["app.py"]
