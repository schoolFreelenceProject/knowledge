from collections.abc import Iterable

from app.schemas.documents import DocumentChunk, EmbeddedChunk


class EmbeddingServiceError(RuntimeError):
    """Raised when embeddings cannot be generated."""


class SentenceTransformersEmbeddingService:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None

    def embed_chunks(self, chunks: Iterable[DocumentChunk]) -> list[EmbeddedChunk]:
        chunk_list = list(chunks)
        if not chunk_list:
            return []

        vectors = self.embed_texts(chunk.text for chunk in chunk_list)
        return [
            EmbeddedChunk(
                vector=vector,
                text=chunk.text,
                metadata=chunk.metadata,
            )
            for chunk, vector in zip(chunk_list, vectors, strict=True)
        ]

    def embed_texts(self, texts: Iterable[str]) -> list[list[float]]:
        text_list = list(texts)
        if not text_list:
            return []

        model = self._load_model()

        try:
            encoded_vectors = model.encode(
                text_list,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise EmbeddingServiceError(
                f"Failed to generate embeddings with model '{self.model_name}': {exc}"
            ) from exc

        return [_to_float_list(vector) for vector in encoded_vectors]

    def _load_model(self):
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingServiceError(
                "Embedding generation requires sentence-transformers. "
                "Install dependencies with `pip install -r requirements.txt`."
            ) from exc

        try:
            self._model = SentenceTransformer(self.model_name)
        except Exception as exc:
            raise EmbeddingServiceError(
                f"Failed to load embedding model '{self.model_name}': {exc}"
            ) from exc

        return self._model


def _to_float_list(vector) -> list[float]:
    if hasattr(vector, "tolist"):
        vector = vector.tolist()

    return [float(value) for value in vector]
