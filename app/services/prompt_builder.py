from app.schemas.documents import RetrievalResult


class RAGPromptBuilder:
    def build_prompt(
        self,
        question: str,
        retrieval_results: list[RetrievalResult],
    ) -> str:
        normalized_question = question.strip()
        context = self._build_context(retrieval_results)

        return (
            "You are a company document assistant. Answer the user's question "
            "using only the retrieved context below. If the context does not "
            "contain the answer, say that the provided documents do not contain "
            "enough information.\n\n"
            f"Question:\n{normalized_question}\n\n"
            f"Retrieved context:\n{context}\n\n"
            "Answer:"
        )

    def _build_context(self, retrieval_results: list[RetrievalResult]) -> str:
        if not retrieval_results:
            return "No retrieved context."

        context_blocks: list[str] = []
        for index, result in enumerate(retrieval_results, start=1):
            source_label = _build_source_label(result)
            context_blocks.append(
                "\n".join(
                    [
                        f"[{index}] Source: {source_label}",
                        f"Score: {result.score:.6f}",
                        "Text:",
                        result.text,
                    ]
                )
            )

        return "\n\n".join(context_blocks)


def _build_source_label(result: RetrievalResult) -> str:
    metadata = result.metadata
    if metadata.content_type == "code":
        location_parts = []
        if metadata.symbol_name:
            location_parts.append(metadata.symbol_name)
        if metadata.start_line is not None and metadata.end_line is not None:
            location_parts.append(f"lines {metadata.start_line}-{metadata.end_line}")

        location_label = ", ".join(location_parts) if location_parts else "code"
        return f"{result.filename} ({location_label})"

    page_label = (
        f"page {result.page_number}"
        if result.page_number is not None
        else "document"
    )
    return f"{result.filename} ({page_label})"
