"""Tests for the RAG knowledge base and retriever (deterministic fake embeddings)."""

from __future__ import annotations

from src.rag.knowledge import KNOWLEDGE, Retriever


class _FakeEmbeddings:
    """Bag-of-words embeddings over a fixed vocabulary — deterministic, no network."""

    def __init__(self, vocab: list[str]) -> None:
        self._vocab = vocab

    def _vec(self, text: str) -> list[float]:
        low = text.lower()
        return [float(low.count(word)) for word in self._vocab]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


VOCAB = ["solde", "filiere", "nuclear", "consommation", "export", "import", "mwh", "hydro"]


def test_knowledge_base_is_non_empty() -> None:
    assert len(KNOWLEDGE) >= 5
    assert all(isinstance(d, str) and d.strip() for d in KNOWLEDGE)


def test_retriever_returns_k_documents() -> None:
    r = Retriever(_FakeEmbeddings(VOCAB))
    docs = r.retrieve("question", k=3)
    assert len(docs) == 3
    assert all(d in KNOWLEDGE for d in docs)


def test_retriever_ranks_relevant_doc_first() -> None:
    r = Retriever(_FakeEmbeddings(VOCAB))
    top = r.retrieve("que signifie un solde négatif dans les échanges ?", k=1)[0]
    assert "solde" in top.lower()


def test_retriever_matches_filiere_question() -> None:
    r = Retriever(_FakeEmbeddings(VOCAB))
    top = r.retrieve("à quoi correspond la filière NUCLEAR ?", k=2)
    assert any("nuclear" in d.lower() or "filière" in d.lower() for d in top)
