from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., description="User question for the RAG pipeline.")
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of relevant chunks to retrieve.",
    )


class ChatSource(BaseModel):
    filename: str
    page_number: int | None
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]
