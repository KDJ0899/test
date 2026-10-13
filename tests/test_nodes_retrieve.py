# retrieve 노드 단위 테스트. 실제 벡터스토어 대신 가짜 retrieve_docs로 메커니즘만 확인한다.

import agent.nodes.retrieve as retrieve_module
from agent.nodes.retrieve import make_retrieve_node
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage


async def test_retrieve_returns_docs(monkeypatch):
    docs = [Document(page_content="내용", metadata={"source": "faq.md"})]

    async def fake_retrieve_docs(vectorstore, query, k):
        return docs

    monkeypatch.setattr(retrieve_module, "retrieve_docs", fake_retrieve_docs)

    node = make_retrieve_node(vectorstore=object())
    result = await node({"messages": [HumanMessage("환불 되나요")]})

    assert result == {"retrieved_docs": docs}


async def test_retrieve_catches_exception(monkeypatch):
    async def failing_retrieve_docs(vectorstore, query, k):
        raise RuntimeError("vectorstore down")

    monkeypatch.setattr(retrieve_module, "retrieve_docs", failing_retrieve_docs)

    node = make_retrieve_node(vectorstore=object())
    result = await node({"messages": [HumanMessage("환불 되나요")]})

    assert result == {"error": "vectorstore down"}
