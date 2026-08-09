from __future__ import annotations

from dataclasses import dataclass

from app.schemas.documents import ChunkMetadata, DocumentChunk
from app.services.code_parser import CodeSymbol, ParsedCodeFile


class CodeChunkingError(RuntimeError):
    """Raised when parsed code cannot be chunked."""


@dataclass(frozen=True)
class CodeChunkingConfig:
    max_chunk_chars: int = 1600
    overlap_lines: int = 3


def chunk_code_file(
    parsed_file: ParsedCodeFile,
    config: CodeChunkingConfig | None = None,
) -> list[DocumentChunk]:
    config = config or CodeChunkingConfig()
    if config.max_chunk_chars < 1:
        raise CodeChunkingError("max_chunk_chars must be greater than 0.")

    symbols = parsed_file.symbols or [
        CodeSymbol(
            name=None,
            kind="file",
            start_byte=0,
            end_byte=len(parsed_file.text.encode("utf-8")),
            start_line=1,
            end_line=max(parsed_file.text.count("\n") + 1, 1),
            start_char=0,
            end_char=len(parsed_file.text),
        )
    ]

    chunks: list[DocumentChunk] = []
    for symbol in symbols:
        symbol_text = parsed_file.text[symbol.start_char:symbol.end_char].strip("\n")
        if not symbol_text.strip():
            continue

        chunks.extend(
            _split_symbol(
                parsed_file=parsed_file,
                symbol=symbol,
                symbol_text=symbol_text,
                starting_chunk_index=len(chunks) + 1,
                config=config,
            )
        )

    if chunks:
        return chunks

    stripped_text = parsed_file.text.strip()
    if not stripped_text:
        return []

    return [
        _build_chunk(
            parsed_file=parsed_file,
            text=stripped_text,
            chunk_index=1,
            symbol=CodeSymbol(
                name=None,
                kind="file",
                start_byte=0,
                end_byte=len(parsed_file.text.encode("utf-8")),
                start_line=1,
                end_line=max(parsed_file.text.count("\n") + 1, 1),
                start_char=0,
                end_char=len(parsed_file.text),
            ),
            start_line=1,
            end_line=max(parsed_file.text.count("\n") + 1, 1),
            start_char=0,
            end_char=len(parsed_file.text),
        )
    ]


def chunk_code_files(
    parsed_files: list[ParsedCodeFile],
    config: CodeChunkingConfig | None = None,
) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    for parsed_file in parsed_files:
        chunks.extend(chunk_code_file(parsed_file, config=config))

    return [
        chunk.model_copy(
            update={
                "metadata": chunk.metadata.model_copy(
                    update={"chunk_index": index}
                )
            }
        )
        for index, chunk in enumerate(chunks, start=1)
    ]


def _split_symbol(
    parsed_file: ParsedCodeFile,
    symbol: CodeSymbol,
    symbol_text: str,
    starting_chunk_index: int,
    config: CodeChunkingConfig,
) -> list[DocumentChunk]:
    if len(symbol_text) <= config.max_chunk_chars:
        return [
            _build_chunk(
                parsed_file=parsed_file,
                text=symbol_text,
                chunk_index=starting_chunk_index,
                symbol=symbol,
                start_line=symbol.start_line,
                end_line=symbol.end_line,
                start_char=symbol.start_char,
                end_char=symbol.end_char,
            )
        ]

    lines = symbol_text.splitlines()
    chunks: list[DocumentChunk] = []
    window: list[str] = []
    window_start_line = symbol.start_line
    current_line = symbol.start_line
    for line in lines:
        proposed_window = [*window, line]
        if window and len("\n".join(proposed_window)) > config.max_chunk_chars:
            chunk_text = "\n".join(window).strip("\n")
            chunks.append(
                _build_chunk(
                    parsed_file=parsed_file,
                    text=chunk_text,
                    chunk_index=starting_chunk_index + len(chunks),
                    symbol=symbol,
                    start_line=window_start_line,
                    end_line=current_line - 1,
                    start_char=symbol.start_char,
                    end_char=symbol.end_char,
                )
            )
            overlap = window[-config.overlap_lines :] if config.overlap_lines else []
            window = [*overlap, line]
            window_start_line = current_line - len(overlap)
        else:
            window = proposed_window

        current_line += 1

    if window:
        chunks.append(
            _build_chunk(
                parsed_file=parsed_file,
                text="\n".join(window).strip("\n"),
                chunk_index=starting_chunk_index + len(chunks),
                symbol=symbol,
                start_line=window_start_line,
                end_line=current_line - 1,
                start_char=symbol.start_char,
                end_char=symbol.end_char,
            )
        )

    return chunks


def _build_chunk(
    parsed_file: ParsedCodeFile,
    text: str,
    chunk_index: int,
    symbol: CodeSymbol,
    start_line: int,
    end_line: int,
    start_char: int,
    end_char: int,
) -> DocumentChunk:
    return DocumentChunk(
        text=text,
        metadata=ChunkMetadata(
            filename=parsed_file.file_path,
            source_path=parsed_file.source_path,
            file_type="code",
            content_type="code",
            page_number=None,
            chunk_index=chunk_index,
            start_char=start_char,
            end_char=end_char,
            repo_name=parsed_file.repo_name,
            repo_url=parsed_file.repo_url,
            branch=parsed_file.branch,
            commit_sha=parsed_file.commit_sha,
            language=parsed_file.language,
            symbol_name=symbol.name,
            symbol_kind=symbol.kind,
            start_line=start_line,
            end_line=end_line,
            repository_file_path=parsed_file.file_path,
        ),
    )
