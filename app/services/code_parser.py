from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
}

SYMBOL_KIND_BY_NODE_TYPE = {
    "function_definition": "function",
    "class_definition": "class",
    "decorated_definition": "decorated_definition",
    "function_declaration": "function",
    "method_definition": "method",
    "class_declaration": "class",
    "lexical_declaration": "declaration",
    "variable_declaration": "declaration",
    "interface_declaration": "interface",
    "type_alias_declaration": "type",
    "method_declaration": "method",
    "constructor_declaration": "constructor",
    "enum_declaration": "enum",
    "struct_item": "struct",
    "impl_item": "impl",
    "function_item": "function",
    "function_declarator": "function",
    "class_specifier": "class",
}


class CodeParserError(RuntimeError):
    """Raised when a source code file cannot be parsed."""


@dataclass(frozen=True)
class CodeSymbol:
    name: str | None
    kind: str
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    start_char: int
    end_char: int


@dataclass(frozen=True)
class ParsedCodeFile:
    repo_url: str
    repo_name: str
    branch: str
    commit_sha: str
    file_path: str
    language: str
    text: str
    file_hash: str
    size_bytes: int
    source_path: str
    symbols: list[CodeSymbol]


class TreeSitterCodeParser:
    def parse_file(
        self,
        file_path: Path,
        repository_root: Path,
        repo_url: str,
        repo_name: str,
        branch: str,
        commit_sha: str,
    ) -> ParsedCodeFile:
        language = detect_language(file_path)
        if language is None:
            raise CodeParserError(f"Unsupported code file type: {file_path.suffix}")

        try:
            raw_bytes = file_path.read_bytes()
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CodeParserError(f"Code file is not valid UTF-8: {file_path}") from exc
        except OSError as exc:
            raise CodeParserError(f"Failed to read code file '{file_path}': {exc}") from exc

        try:
            from tree_sitter_language_pack import get_parser
        except ImportError as exc:
            raise CodeParserError(
                "Code parsing requires tree-sitter-language-pack. "
                "Install dependencies with `pip install -r requirements.txt`."
            ) from exc

        try:
            parser = get_parser(language)
            tree = parser.parse(raw_bytes)
        except Exception as exc:
            raise CodeParserError(
                f"Failed to parse '{file_path}' as {language}: {exc}"
            ) from exc

        repository_root = repository_root.resolve()
        relative_path = _relative_path(file_path=file_path, repository_root=repository_root)
        return ParsedCodeFile(
            repo_url=repo_url,
            repo_name=repo_name,
            branch=branch,
            commit_sha=commit_sha,
            file_path=relative_path,
            language=language,
            text=text,
            file_hash=hashlib.sha256(raw_bytes).hexdigest(),
            size_bytes=len(raw_bytes),
            source_path=f"{repo_name}@{commit_sha}/{relative_path}",
            symbols=_collect_symbols(tree.root_node, text=text, raw_bytes=raw_bytes),
        )


def detect_language(file_path: Path) -> str | None:
    return LANGUAGE_BY_SUFFIX.get(file_path.suffix.lower())


def _collect_symbols(root_node: Any, text: str, raw_bytes: bytes) -> list[CodeSymbol]:
    symbols: list[CodeSymbol] = []
    stack = list(root_node.children)

    while stack:
        node = stack.pop(0)
        symbol_kind = SYMBOL_KIND_BY_NODE_TYPE.get(node.type)
        if symbol_kind is not None:
            symbols.append(
                CodeSymbol(
                    name=_extract_symbol_name(node),
                    kind=symbol_kind,
                    start_byte=node.start_byte,
                    end_byte=node.end_byte,
                    start_line=node.start_point.row + 1,
                    end_line=node.end_point.row + 1,
                    start_char=_byte_to_char_offset(raw_bytes, text, node.start_byte),
                    end_char=_byte_to_char_offset(raw_bytes, text, node.end_byte),
                )
            )

        stack.extend(node.children)

    return _deduplicate_symbols(symbols)


def _extract_symbol_name(node: Any) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node is not None and name_node.text is not None:
        return name_node.text.decode("utf-8", errors="replace")

    for child in node.children:
        if child.type in {"identifier", "property_identifier", "type_identifier"}:
            return child.text.decode("utf-8", errors="replace")

    return None


def _deduplicate_symbols(symbols: list[CodeSymbol]) -> list[CodeSymbol]:
    seen: set[tuple[int, int, str]] = set()
    deduplicated: list[CodeSymbol] = []
    for symbol in symbols:
        key = (symbol.start_byte, symbol.end_byte, symbol.kind)
        if key in seen:
            continue

        seen.add(key)
        deduplicated.append(symbol)

    return sorted(deduplicated, key=lambda symbol: (symbol.start_byte, symbol.end_byte))


def _byte_to_char_offset(raw_bytes: bytes, text: str, byte_offset: int) -> int:
    if byte_offset <= 0:
        return 0

    if byte_offset >= len(raw_bytes):
        return len(text)

    return len(raw_bytes[:byte_offset].decode("utf-8", errors="ignore"))


def _relative_path(file_path: Path, repository_root: Path) -> str:
    try:
        return file_path.resolve().relative_to(repository_root).as_posix()
    except ValueError as exc:
        raise CodeParserError(
            f"Code file path escapes repository root: {file_path}"
        ) from exc
