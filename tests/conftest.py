import pytest

from assistant.ingest import build_index
from assistant.store import VectorStore
from tests.fakes import FakeEmbedder


@pytest.fixture
def embedder():
    return FakeEmbedder()


@pytest.fixture
def store(tmp_path, embedder):
    """A vector store with the real help pages, indexed with the fake embedder."""
    store = VectorStore(path=tmp_path / "index")
    build_index(store, embedder)
    return store
