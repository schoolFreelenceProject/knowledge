from collections.abc import Iterable
from dataclasses import dataclass

from app.schemas.documents import ChunkMetadata, DocumentChunk, ExtractedDocument


@dataclass(frozen=True)
class ChunkingConfig:
    chunk_size: int
    chunk_overlap: int

    def __post_init__(self) -> None:
        if self.chunk_size < 1:
            raise ValueError("chunk_size must be greater than 0.")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap cannot be negative.")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size.")


def chunk_documents(
    documents: Iterable[ExtractedDocument],
    config: ChunkingConfig,
) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []

    for document in documents:
        chunks.extend(chunk_document(document=document, config=config))

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


def chunk_document(
    document: ExtractedDocument,
    config: ChunkingConfig,
) -> list[DocumentChunk]:
    text = document.text
    if not text.strip():
        return []

    chunks: list[DocumentChunk] = []
    position = 0

    while position < len(text):
        raw_end = min(position + config.chunk_size, len(text))
        end = (
            _find_split_boundary(text=text, start=position, raw_end=raw_end)
            if raw_end < len(text)
            else raw_end
        )
        chunk_text, start_char, end_char = _trim_slice(
            text=text,
            start=position,
            end=end,
        )

        if chunk_text:
            chunks.append(
                DocumentChunk(
                    text=chunk_text,
                    metadata=ChunkMetadata(
                        **document.metadata.model_dump(),
                        chunk_index=len(chunks) + 1,
                        start_char=start_char,
                        end_char=end_char,
                    ),
                )
            )

        if raw_end >= len(text):
            break

        previous_position = position
        proposed_position = max(position + 1, end - config.chunk_overlap)
        position = _snap_start_to_boundary(
            text=text,
            proposed_start=proposed_position,
            minimum_start=previous_position + 1,
        )

        if position <= previous_position:
            position = previous_position + 1

    return chunks


def _find_split_boundary(text: str, start: int, raw_end: int) -> int:
    window_size = raw_end - start
    search_floor = start + max(1, int(window_size * 0.6))

    for boundary in ("\n\n", "\n", ". ", "; ", ": ", " "):
        boundary_index = text.rfind(boundary, search_floor, raw_end)
        if boundary_index != -1:
            return boundary_index + len(boundary)

    return raw_end


def _trim_slice(text: str, start: int, end: int) -> tuple[str, int, int]:
    while start < end and text[start].isspace():
        start += 1

    while end > start and text[end - 1].isspace():
        end -= 1

    return text[start:end], start, end


def _snap_start_to_boundary(
    text: str,
    proposed_start: int,
    minimum_start: int,
) -> int:
    if proposed_start <= minimum_start:
        return proposed_start

    search_floor = max(minimum_start, proposed_start - 80)

    for boundary in ("\n\n", "\n", ". ", "; ", ": ", " "):
        boundary_index = text.rfind(boundary, search_floor, proposed_start)
        if boundary_index != -1:
            return boundary_index + len(boundary)

    return proposed_start
