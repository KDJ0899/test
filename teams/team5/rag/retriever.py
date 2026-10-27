# 벡터스토어 생성/검색. 기본은 InMemoryVectorStore지만, 교체 가능하게 함수 하나로 감싼다 (CLAUDE.md 2장).

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore, VectorStore


def build_vectorstore(docs: list[Document], embeddings: Embeddings) -> VectorStore:
    """다른 벡터스토어로 바꾸려면 이 함수만 교체하면 된다."""
    store = InMemoryVectorStore(embeddings)
    store.add_documents(docs)
    return store


def retrieve_docs(vectorstore: VectorStore, query: str, k: int) -> list[Document]:
    return vectorstore.similarity_search(query, k=k)
