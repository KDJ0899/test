# respond 노드 단위 테스트.

from agent.nodes.respond import respond_node
from langchain_core.documents import Document
from langchain_core.messages import AIMessage


async def test_respond_without_docs_is_noop():
    state = {"messages": [AIMessage(content="답변")], "retrieved_docs": []}
    assert await respond_node(state) == {}


async def test_respond_with_docs_appends_sources():
    ai_message = AIMessage(content="답변입니다", id="ai-1")
    docs = [
        Document(page_content="...", metadata={"source": "faq.md"}),
        Document(page_content="...", metadata={"source": "notice.md"}),
    ]
    state = {"messages": [ai_message], "retrieved_docs": docs}

    result = await respond_node(state)

    updated = result["messages"][0]
    assert updated.id == "ai-1"  # add_messages가 같은 메시지로 치환하도록 id 유지
    assert "답변입니다" in updated.content
    assert "faq.md" in updated.content
    assert "notice.md" in updated.content
