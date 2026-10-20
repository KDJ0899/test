# 테스트 공용 도우미. 실제 LLM/임베딩 없이 "대본(script)대로 답하는 가짜 모델"로 그래프 메커니즘만 검증한다.

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.messages import AIMessage


class ScriptedLLM:
    """호출될 때마다 준비된 응답을 순서대로 돌려주는 가짜 채팅 모델. 호출 때 받은 messages도 기록한다."""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls: list[list] = []

    def bind_tools(self, tools):
        return self

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages, **kwargs):
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("ScriptedLLM: 준비된 응답이 없다 (예상보다 LLM이 더 호출됨)")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def tool_call_message(name: str, args: dict, call_id: str = "call-1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


@pytest.fixture
def fake_llms(monkeypatch):
    """노드 모듈마다 get_llm을 가짜로 바꾼다. 반환값 dict의 각 ScriptedLLM에 responses를 채워 쓴다."""
    import teams.team5.nodes.agent as agent_mod
    import teams.team5.nodes.classify as classify_mod

    llms = {"classify": ScriptedLLM(), "agent": ScriptedLLM()}
    monkeypatch.setattr(classify_mod, "get_llm", lambda **kw: llms["classify"])
    monkeypatch.setattr(agent_mod, "get_llm", lambda **kw: llms["agent"])
    for name in ("extract", "plan"):
        try:
            mod = __import__(f"teams.team5.nodes.{'extract_preferences' if name == 'extract' else 'plan_trip'}", fromlist=["x"])
        except ModuleNotFoundError:
            continue
        llms[name] = ScriptedLLM()
        monkeypatch.setattr(mod, "get_llm", lambda llm=llms[name], **kw: llm)
    return llms


@pytest.fixture
def fake_embeddings(monkeypatch):
    import teams.team5.workflow as graph_mod

    if hasattr(graph_mod, "get_embeddings"):
        monkeypatch.setattr(graph_mod, "get_embeddings", lambda: DeterministicFakeEmbedding(size=8))
