from app.schemas.documents import ChunkMetadata
from app.services.bm25_retrieval_service import BM25RetrievalService, _tokenize
from app.services.vector_store import RetrievalDocument


class FakeVectorStore:
    def __init__(self, documents: list[RetrievalDocument]) -> None:
        self.documents = documents
        self.calls = 0

    def list_retrieval_documents(self):
        self.calls += 1
        return self.documents


def _build_document(
    point_id: str,
    filename: str,
    text: str,
    chunk_index: int = 1,
) -> RetrievalDocument:
    return RetrievalDocument(
        point_id=point_id,
        text=text,
        metadata=ChunkMetadata(
            filename=filename,
            source_path=filename,
            file_type="markdown",
            page_number=None,
            chunk_index=chunk_index,
            start_char=0,
            end_char=len(text),
        ),
    )


def test_bm25_retrieval_returns_keyword_matches() -> None:
    vector_store = FakeVectorStore(
        [
            _build_document(
                point_id="point-1",
                filename="company_policy.md",
                text="Employees may work remotely with manager approval.",
            ),
            _build_document(
                point_id="point-2",
                filename="expense_policy.md",
                text="Receipts are required for expense reimbursement.",
            ),
        ]
    )
    bm25_service = BM25RetrievalService(vector_store=vector_store)

    results = bm25_service.retrieve(
        query="remote work manager",
        top_k=2,
    )

    assert [result.filename for result in results] == ["company_policy.md"]
    assert results[0].score > 0
    assert vector_store.calls == 1


def test_bm25_retrieval_honors_allowed_point_ids() -> None:
    vector_store = FakeVectorStore(
        [
            _build_document(
                point_id="point-1",
                filename="company_policy.md",
                text="Employees may work remotely with manager approval.",
            ),
            _build_document(
                point_id="point-2",
                filename="expense_policy.md",
                text="Receipts are required for expense reimbursement.",
            ),
        ]
    )
    bm25_service = BM25RetrievalService(vector_store=vector_store)

    results = bm25_service.retrieve(
        query="receipts reimbursement",
        top_k=2,
        allowed_point_ids=["point-2"],
    )
    blocked_results = bm25_service.retrieve(
        query="receipts reimbursement",
        top_k=2,
        allowed_point_ids=["point-1"],
    )

    assert [result.filename for result in results] == ["expense_policy.md"]
    assert blocked_results == []
    assert vector_store.calls == 1


def test_bm25_retrieval_empty_allowed_point_filter_returns_no_results() -> None:
    bm25_service = BM25RetrievalService(
        vector_store=FakeVectorStore(
            [
                _build_document(
                    point_id="point-1",
                    filename="company_policy.md",
                    text="Employees may work remotely.",
                )
            ]
        )
    )

    assert bm25_service.retrieve("remote", top_k=3, allowed_point_ids=[]) == []


def test_bm25_tokenizer_generates_japanese_tokens() -> None:
    tokens = _tokenize("経費精算とカタカナ")

    assert "経費精算" in tokens
    assert "経費" in tokens
    assert "カタカナ" in tokens
    assert "カタ" in tokens


def test_bm25_retrieval_matches_japanese_kanji_terms() -> None:
    vector_store = FakeVectorStore(
        [
            _build_document(
                point_id="point-1",
                filename="expense_policy.md",
                text="経費精算には領収書の添付が必要です。",
            ),
            _build_document(
                point_id="point-2",
                filename="leave_policy.md",
                text="有給休暇は上長の承認が必要です。",
            ),
        ]
    )
    bm25_service = BM25RetrievalService(vector_store=vector_store)

    results = bm25_service.retrieve(query="経費精算", top_k=2)

    assert [result.filename for result in results] == ["expense_policy.md"]


def test_bm25_retrieval_normalizes_kana_and_full_width_latin() -> None:
    vector_store = FakeVectorStore(
        [
            _build_document(
                point_id="point-1",
                filename="network.md",
                text="VPN 接続とカタカナ表記の確認を行います。",
            )
        ]
    )
    bm25_service = BM25RetrievalService(vector_store=vector_store)

    kana_results = bm25_service.retrieve(query="ｶﾀｶﾅ", top_k=1)
    mixed_results = bm25_service.retrieve(query="ＶＰＮ　接続", top_k=1)

    assert [result.filename for result in kana_results] == ["network.md"]
    assert [result.filename for result in mixed_results] == ["network.md"]


def test_bm25_retrieval_matches_hiragana_terms() -> None:
    vector_store = FakeVectorStore(
        [
            _build_document(
                point_id="point-1",
                filename="guide.md",
                text="ひらがなの検索テストを追加します。",
            )
        ]
    )
    bm25_service = BM25RetrievalService(vector_store=vector_store)

    results = bm25_service.retrieve(query="ひらがな", top_k=1)

    assert [result.filename for result in results] == ["guide.md"]
