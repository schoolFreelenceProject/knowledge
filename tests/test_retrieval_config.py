import pytest

from app.core.config import get_settings


def test_retrieval_config_defaults_to_vector(monkeypatch) -> None:
    monkeypatch.delenv("RETRIEVAL_MODE", raising=False)
    monkeypatch.delenv("RERANKER_ENABLED", raising=False)

    settings = get_settings()

    assert settings.retrieval_mode == "vector"
    assert settings.hybrid_fusion_strategy == "rrf"
    assert settings.reranker_enabled is False


def test_retrieval_config_validates_mode(monkeypatch) -> None:
    monkeypatch.setenv("RETRIEVAL_MODE", "rerank")

    with pytest.raises(ValueError):
        get_settings()


def test_retrieval_config_reads_reranker_settings(monkeypatch) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "true")
    monkeypatch.setenv("RERANKER_MODEL_NAME", "cross-encoder/test-model")
    monkeypatch.setenv("RERANKER_CANDIDATE_SIZE", "12")
    monkeypatch.setenv("RERANKER_BATCH_SIZE", "4")

    settings = get_settings()

    assert settings.reranker_enabled is True
    assert settings.reranker_model_name == "cross-encoder/test-model"
    assert settings.reranker_candidate_size == 12
    assert settings.reranker_batch_size == 4
