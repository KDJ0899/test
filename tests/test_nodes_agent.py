# agent 노드 단위 테스트. 실제 LLM 호출 없이 가짜 모델로 메커니즘만 확인한다.

import agent.nodes.agent as agent_module
from agent.nodes.agent import make_agent_node
from agent.tools.local_tools import calculate
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage


class FakeLLM:
    def __init__(self, name, calls, response=None, raise_exc=None):
        self.name = name
        self.calls = calls
        self.response = response
        self.raise_exc = raise_exc

    def bind_tools(self, tools):
        return FakeLLM("with_tools", self.calls, self.response, self.raise_exc)

    async def ainvoke(self, messages, **kwargs):
        self.calls.append((self.name, messages))
        if self.raise_exc:
            raise self.raise_exc
        return self.response


async def test_agent_uses_plain_llm_for_chat_intent(monkeypatch):
    calls = []
    fake = FakeLLM("plain", calls, response=AIMessage(content="ok"))
    monkeypatch.setattr(agent_module, "get_llm", lambda: fake)

    node = make_agent_node(tools=[calculate])
    result = await node({"messages": [HumanMessage("안녕")], "intent": "chat"})

    assert calls[-1][0] == "plain"
    assert result["messages"][0].content == "ok"


async def test_agent_uses_tool_bound_llm_for_tool_intent(monkeypatch):
    calls = []
    fake = FakeLLM("plain", calls, response=AIMessage(content="ok"))
    monkeypatch.setattr(agent_module, "get_llm", lambda: fake)

    node = make_agent_node(tools=[calculate])
    await node({"messages": [HumanMessage("3+4 계산해줘")], "intent": "tool"})

    assert calls[-1][0] == "with_tools"


async def test_agent_injects_rag_context_when_docs_present(monkeypatch):
    calls = []
    fake = FakeLLM("plain", calls, response=AIMessage(content="ok"))
    monkeypatch.setattr(agent_module, "get_llm", lambda: fake)

    node = make_agent_node(tools=[])
    docs = [Document(page_content="환불은 7일 이내 가능합니다.", metadata={"source": "faq.md"})]
    await node({"messages": [HumanMessage("환불 되나요")], "intent": "rag", "retrieved_docs": docs})

    sent_messages = calls[-1][1]
    assert any("환불은 7일 이내 가능합니다." in m.content for m in sent_messages)


async def test_agent_catches_llm_exception(monkeypatch):
    calls = []
    fake = FakeLLM("plain", calls, raise_exc=RuntimeError("llm down"))
    monkeypatch.setattr(agent_module, "get_llm", lambda: fake)

    node = make_agent_node(tools=[])
    result = await node({"messages": [HumanMessage("안녕")], "intent": "chat"})

    assert result == {"error": "llm down"}
