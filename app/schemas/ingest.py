from pydantic import BaseModel, Field


class IngestResponse(BaseModel):
    document_id: int
    filename: str
    file_type: str
    storage_path: str
    file_hash: str
    status: str
    extracted_blocks: int = Field(..., ge=0)
    chunks: int = Field(..., ge=0)
    embeddings: int = Field(..., ge=0)
    collection_name: str
    stored_vectors: int = Field(..., ge=0)
    saved_chunks: int = Field(..., ge=0)
    vector_size: int | None
