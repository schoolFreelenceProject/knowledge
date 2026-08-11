from pathlib import Path

from app.services.code_chunker import CodeChunkingConfig, chunk_code_file
from app.services.code_parser import TreeSitterCodeParser


def test_tree_sitter_parser_extracts_python_symbols(tmp_path) -> None:
    code_path = tmp_path / "auth_service.py"
    code_path.write_text(
        "\n".join(
            [
                "class AuthService:",
                "    def login(self, email):",
                "        return email.lower()",
                "",
                "def normalize_email(email):",
                "    return email.strip().lower()",
            ]
        ),
        encoding="utf-8",
    )

    parsed_file = TreeSitterCodeParser().parse_file(
        file_path=code_path,
        repository_root=tmp_path,
        repo_url="file:///repo",
        repo_name="repo",
        branch="main",
        commit_sha="a" * 40,
    )

    assert parsed_file.language == "python"
    assert parsed_file.file_path == "auth_service.py"
    assert [(symbol.kind, symbol.name) for symbol in parsed_file.symbols] == [
        ("class", "AuthService"),
        ("function", "login"),
        ("function", "normalize_email"),
    ]


def test_cpp_parser_uses_file_level_fallback(tmp_path) -> None:
    code_path = tmp_path / "lio_node.cpp"
    code_path.write_text(
        "\n".join(
            [
                "#include <iostream>",
                "int main() {",
                "    std::cout << \"ok\" << std::endl;",
                "    return 0;",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    parsed_file = TreeSitterCodeParser().parse_file(
        file_path=code_path,
        repository_root=tmp_path,
        repo_url="file:///repo",
        repo_name="repo",
        branch="main",
        commit_sha="a" * 40,
    )
    chunks = chunk_code_file(
        parsed_file,
        config=CodeChunkingConfig(max_chunk_chars=1000, overlap_lines=1),
    )

    assert parsed_file.language == "cpp"
    assert parsed_file.symbols == []
    assert chunks
    assert chunks[0].metadata.symbol_kind == "file"
    assert chunks[0].metadata.repository_file_path == "lio_node.cpp"


def test_php_parser_uses_file_level_fallback(tmp_path) -> None:
    code_path = tmp_path / "Controller.php"
    code_path.write_text(
        "<?php\nclass Controller {\n    public function index() { return 'ok'; }\n}\n",
        encoding="utf-8",
    )

    parsed_file = TreeSitterCodeParser().parse_file(
        file_path=code_path,
        repository_root=tmp_path,
        repo_url="file:///repo",
        repo_name="repo",
        branch="main",
        commit_sha="a" * 40,
    )
    chunks = chunk_code_file(
        parsed_file,
        config=CodeChunkingConfig(max_chunk_chars=1000, overlap_lines=1),
    )

    assert parsed_file.language == "php"
    assert parsed_file.symbols == []
    assert chunks
    assert chunks[0].metadata.symbol_kind == "file"
    assert chunks[0].metadata.repository_file_path == "Controller.php"


def test_code_chunker_preserves_code_metadata() -> None:
    parser = TreeSitterCodeParser()
    test_file_path = Path(__file__)
    parsed_file = parser.parse_file(
        file_path=test_file_path,
        repository_root=test_file_path.parent.parent,
        repo_url="file:///company-document-rag",
        repo_name="company-document-rag",
        branch="main",
        commit_sha="b" * 40,
    )

    chunks = chunk_code_file(
        parsed_file,
        config=CodeChunkingConfig(max_chunk_chars=4000, overlap_lines=1),
    )

    assert chunks
    first_chunk = chunks[0]
    assert first_chunk.metadata.content_type == "code"
    assert first_chunk.metadata.file_type == "code"
    assert first_chunk.metadata.page_number is None
    assert first_chunk.metadata.repo_name == "company-document-rag"
    assert first_chunk.metadata.commit_sha == "b" * 40
    assert first_chunk.metadata.language == "python"
    assert first_chunk.metadata.repository_file_path == "tests/test_code_parser_chunker.py"
    assert first_chunk.metadata.start_line is not None
    assert first_chunk.metadata.end_line is not None
