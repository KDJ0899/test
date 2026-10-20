# 개별 노드 단위 테스트: classify 초기화 규칙, ingest 중복 방지, error 노드, respond 출처.

import json

from teams.team5.nodes.classify import IntentClassification, make_classify_node
from teams.team5.nodes.error import error_node
from teams.team5.nodes.ingest_tool_results import ingest_tool_results_node
from teams.team5.nodes.respond import respond_node
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


async def test_classify_resets_turn_values_but_not_trip_state(fake_llms):
    fake_llms["classify"].responses = [IntentClassification(intent="trip")]
    out = await make_classify_node()({"user_input": "안녕", "answer": "old", "error": "old", "missing_fields": ["team"],
                                      "trip_preferences": {"team": "롯데"}, "messages": []})
    assert out["answer"] == "" and out["error"] is None and out["missing_fields"] == []
    assert out["intent"] == "trip" and [m.content for m in out["messages"]] == ["안녕"]
    assert "trip_preferences" not in out  # 여행 상태는 건드리지 않는다


async def test_classify_skips_llm_when_approval_pending(fake_llms):
    out = await make_classify_node()({"user_input": "승인", "pending_approval": {"approval_id": "a"}, "messages": []})
    assert out["intent"] is None and not fake_llms["classify"].calls


async def test_classify_llm_failure_goes_to_error(fake_llms):
    fake_llms["classify"].responses = [RuntimeError("boom")]
    out = await make_classify_node()({"user_input": "x", "messages": []})
    assert out["error"] == "boom" and len(out["messages"]) == 1


def tool_msg(call_id, name, payload):
    return ToolMessage(content=json.dumps(payload), tool_call_id=call_id, name=name)


async def test_ingest_caches_once_and_tracks_call_ids():
    events = [{"id": "e1"}, {"id": "e2"}]
    state = {"intent": "trip", "messages": [HumanMessage("q"), tool_msg("c1", "search_sports_events",
             {"status": "ok", "source": "s", "data": {"events": events}})]}
    out = await ingest_tool_results_node(state)
    assert out["sports_events"] == events and out["processed_tool_call_ids"] == ["c1"] and out["tool_iterations"] == 1
    assert out["trip_status"] == "selecting"

    # 이미 처리한 호출 ID는 다시 반영하지 않는다
    again = await ingest_tool_results_node({**state, **out, "sports_events": [{"id": "stale"}]})
    assert "sports_events" not in again and again["processed_tool_call_ids"] == ["c1"]


async def test_ingest_ignores_error_results_and_non_trip_lookups():
    err = tool_msg("c1", "search_sports_events", {"status": "error", "error": "x"})
    assert "sports_events" not in await ingest_tool_results_node({"intent": "trip", "messages": [HumanMessage("q"), err]})
    ok = tool_msg("c2", "search_sports_events", {"status": "ok", "source": "s", "data": {"events": [{"id": "e"}]}})
    out = await ingest_tool_results_node({"intent": "qa", "messages": [HumanMessage("q"), ok]})
    assert "sports_events" not in out


async def test_ingest_drops_selection_missing_from_new_candidates():
    ok = tool_msg("c1", "search_sports_events", {"status": "ok", "source": "s", "data": {"events": [{"id": "new"}]}})
    state = {"intent": "trip", "selected_event_id": "old", "sports_events": [{"id": "old"}], "trip_plan": {"x": 1},
             "messages": [HumanMessage("q"), ok]}
    out = await ingest_tool_results_node(state)
    assert out["selected_event_id"] is None and out["trip_plan"] is None


async def test_ingest_ignores_tool_messages_from_previous_turns():
    old = tool_msg("old", "search_places", {"status": "ok", "source": "s", "data": {"places": [{"id": "p"}]}})
    out = await ingest_tool_results_node({"intent": "trip", "messages": [old, AIMessage("x"), HumanMessage("새 질문")]})
    assert "places" not in out and out["processed_tool_call_ids"] == []


async def test_error_node_fills_dangling_tool_calls_and_explains():
    call = AIMessage(content="", tool_calls=[{"name": "search_places", "args": {}, "id": "c1", "type": "tool_call"}])
    out = await error_node({"messages": [HumanMessage("q"), call], "error": "tools exploded"})
    assert "tools exploded" in out["answer"]
    assert out["messages"][0].tool_call_id == "c1" and out["messages"][-1].content == out["answer"]


async def test_respond_appends_rag_sources():
    docs = [Document(page_content="a", metadata={"source": "baseball_guide.md"}),
            Document(page_content="b", metadata={"source": "travel_guide.md"})]
    out = await respond_node({"messages": [AIMessage("답")], "retrieved_docs": docs})
    assert out["answer"] == "답\n\n출처: baseball_guide.md, travel_guide.md"
    assert (await respond_node({"messages": [AIMessage("답")]}))["answer"] == "답"


async def test_ingest_guide_docs_for_any_intent_and_search_guide_tool_format(fake_embeddings):
    from teams.team5.rag.guide_tool import make_search_guide_tool
    from teams.team5.rag.retriever import build_vectorstore
    from langchain_core.embeddings import DeterministicFakeEmbedding

    store = await build_vectorstore([Document(page_content="준비물 안내", metadata={"source": "baseball_guide.md"})],
                                    DeterministicFakeEmbedding(size=8))
    raw = await make_search_guide_tool(store).ainvoke({"query": "준비물"})
    assert json.loads(raw)["data"]["docs"][0]["source"] == "baseball_guide.md"

    msg = ToolMessage(content=raw, tool_call_id="g1", name="search_guide_docs")
    out = await ingest_tool_results_node({"intent": "qa", "messages": [HumanMessage("q"), msg]})
    assert out["retrieved_docs"][0].metadata["source"] == "baseball_guide.md"


async def test_retrieve_node_user_query_and_dedupes_with_existing_docs(monkeypatch):
    import teams.team5.nodes.retrieve as mod

    seen = {}

    async def fake_retrieve_docs(store, query, k):
        seen["query"] = query
        return [Document(page_content="old", metadata={"source": "a.md"}), Document(page_content="new", metadata={"source": "b.md"})]

    monkeypatch.setattr(mod, "retrieve_docs", fake_retrieve_docs)
    state = {"user_input": "준비물?", "retrieved_docs": [Document(page_content="old", metadata={"source": "a.md"})]}
    out = await mod.make_retrieve_node(object())(state)
    assert seen["query"] == "준비물?" and [d.page_content for d in out["retrieved_docs"]] == ["old", "new"]


async def test_retrieve_for_plan_uses_fixed_query_from_transport(monkeypatch):
    import teams.team5.nodes.retrieve as mod

    seen = {}

    async def fake_retrieve_docs(store, query, k):
        seen["query"] = query
        return []

    monkeypatch.setattr(mod, "retrieve_docs", fake_retrieve_docs)
    node = mod.make_retrieve_node(object(), for_plan=True)
    await node({"user_input": "무시됨", "trip_preferences": {"transport": "public_transit"}})
    assert "대중교통" in seen["query"] and "무시됨" not in seen["query"]


async def test_retrieve_failure_goes_to_error(monkeypatch):
    import teams.team5.nodes.retrieve as mod

    async def boom(*a, **kw):
        raise RuntimeError("store down")

    monkeypatch.setattr(mod, "retrieve_docs", boom)
    assert await mod.make_retrieve_node(object())({"user_input": "q"}) == {"error": "store down"}
