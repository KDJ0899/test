# classify 노드 단위 테스트. 실제 LLM 호출 없이 가짜 structured output으로 분류 로직만 확인한다.

import agent.nodes.classify as classify_module
from agent.nodes.classify import IntentClassification, make_classify_node
from langchain_core.messages import HumanMessage


class FakeStructuredLLM:
    def __init__(self, result=None, raise_exc=None):
        self.result = result
        self.raise_exc = raise_exc

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages, **kwargs):
        if self.raise_exc:
            raise self.raise_exc
        return self.result


async def test_classify_sets_intent_and_resets_fields(monkeypatch):
    fake = FakeStructuredLLM(result=IntentClassification(intent="tool"))
    monkeypatch.setattr(classify_module, "get_llm", lambda: fake)

    node = make_classify_node()
    result = await node({"messages": [HumanMessage("3+4 계산해줘")]})

    assert result == {"intent": "tool", "retrieved_docs": [], "error": None}


async def test_classify_catches_exception(monkeypatch):
    fake = FakeStructuredLLM(raise_exc=RuntimeError("classify down"))
    monkeypatch.setattr(classify_module, "get_llm", lambda: fake)

    node = make_classify_node()
    result = await node({"messages": [HumanMessage("안녕")]})

    assert result == {"error": "classify down"}
