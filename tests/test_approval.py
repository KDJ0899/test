# HITL(대화형 승인) 테스트 (T08, T09, T11, T12 + 승인 재사용/임의 Tool 방지).

import json

import teams.team5.tools.local_tools as lt
import pytest
from teams.team5.workflow import build_graph
from teams.team5.nodes.approval import (
    execute_approved_tool_node,
    is_affirmative,
    is_negative,
    resolve_approval_node,
)
from teams.team5.nodes.extract_preferences import PreferenceUpdate
from langchain_core.messages import AIMessage
from tests.conftest import tool_call_message
from tests.test_multiturn import CONFIG, intents, run_until_completed, values


@pytest.fixture
async def ctx(fake_llms, fake_embeddings, monkeypatch, tmp_path):
    saved = tmp_path / "saved_trips.json"
    monkeypatch.setattr(lt, "SAVED_TRIPS_PATH", saved)
    return await build_graph(), fake_llms, saved


async def ask_save(graph, llms):
    llms["classify"].responses += intents("qa")
    llms["agent"].responses += [tool_call_message("save_trip_plan", {"trip_plan": {"title": "LLM이 지어낸 인자"}})]
    return await graph.ainvoke({"user_input": "일정 저장해줘"}, CONFIG)


def test_answer_words():
    assert is_affirmative("승인") and is_affirmative(" 예. ") and is_affirmative("YES")
    assert is_negative("거절") and is_negative("아니오") and not is_affirmative("글쎄")
    assert not is_affirmative("음 승인할까") and not is_negative("")


async def test_t08_save_requires_approval_then_saves_once(ctx):
    graph, llms, saved = ctx
    await run_until_completed(graph, llms)
    plan = (await values(graph))["trip_plan"]

    r = await ask_save(graph, llms)
    assert r["answer"].startswith("[승인 요청]") and "save_trip_plan" in r["answer"]
    assert not saved.exists()  # 승인 전에는 파일을 쓰지 않는다
    pending = (await values(graph))["pending_approval"]
    assert pending["tool_name"] == "save_trip_plan" and pending["approval_id"] and pending["requested_at"]
    assert pending["arguments"] == {"trip_plan": plan}  # LLM이 만든 인자가 아니라 State의 일정으로 고정

    r = await graph.ainvoke({"user_input": "승인"}, CONFIG)  # 승인 대기 중에는 분류 LLM을 부르지 않는다
    assert "저장했어요" in r["answer"]
    data = json.loads(saved.read_text(encoding="utf-8"))
    assert len(data) == 1 and data[0]["trip_plan"] == plan
    assert (await values(graph))["pending_approval"] is None

    # 같은 승인으로 다시 실행되지 않는다: "승인"을 또 보내면 일반 요청으로 분류된다 (대기 중인 승인이 없다).
    llms["classify"].responses += intents("chat")
    llms["agent"].responses += [AIMessage(content="무엇을 도와드릴까요?")]
    await graph.ainvoke({"user_input": "승인"}, CONFIG)
    assert len(json.loads(saved.read_text(encoding="utf-8"))) == 1


async def test_t09_reject_does_not_save(ctx):
    graph, llms, saved = ctx
    await run_until_completed(graph, llms)
    await ask_save(graph, llms)
    r = await graph.ainvoke({"user_input": "거절"}, CONFIG)
    assert "실행하지 않았" in r["answer"]
    assert not saved.exists() and (await values(graph))["pending_approval"] is None
    assert (await values(graph))["trip_plan"] is not None  # 일정 자체는 그대로


async def test_t12_other_request_while_pending_never_executes_old_approval(ctx):
    graph, llms, saved = ctx
    await run_until_completed(graph, llms)
    await ask_save(graph, llms)

    r = await graph.ainvoke({"user_input": "야구장 준비물은?"}, CONFIG)  # 승인도 거절도 아닌 다른 요청
    assert "승인" in r["answer"] and "거절" in r["answer"] and not saved.exists()
    assert (await values(graph))["pending_approval"] is not None  # 대기는 유지, 실행은 안 됨

    await graph.ainvoke({"user_input": "취소"}, CONFIG)  # 거절해야 다른 요청으로 넘어갈 수 있다
    assert not saved.exists() and (await values(graph))["pending_approval"] is None


async def test_save_without_plan_does_not_request_approval(ctx):
    graph, llms, saved = ctx
    r = await ask_save(graph, llms)
    assert "저장할 여행 일정이 아직 없어요" in r["answer"]
    assert (await values(graph)).get("pending_approval") is None


async def test_mixed_tool_calls_do_not_leave_dangling_tool_calls(ctx):
    graph, llms, _ = ctx
    llms["classify"].responses += intents("qa")
    llms["agent"].responses += [AIMessage(content="", tool_calls=[
        {"name": "get_current_datetime", "args": {}, "id": "a", "type": "tool_call"},
        {"name": "save_trip_plan", "args": {"trip_plan": {}}, "id": "b", "type": "tool_call"}])]
    await graph.ainvoke({"user_input": "시간이랑 저장"}, CONFIG)
    messages = (await values(graph))["messages"]
    answered = {m.tool_call_id for m in messages if m.type == "tool"}
    assert answered == {"a", "b"}  # 모든 tool_call에 대응하는 ToolMessage가 있다 (다음 LLM 호출이 깨지지 않음)


async def test_execute_refuses_unknown_or_unapproved_tool():
    for bad in [
        {"approval_id": "x", "tool_name": "rm_rf", "arguments": {}},
        {"approval_id": "x", "tool_name": "search_sports_events", "arguments": {}},  # 승인 대상이 아닌 Tool
        {"tool_name": "save_trip_plan", "arguments": {}},  # approval_id 없음
    ]:
        out = await execute_approved_tool_node({"pending_approval": bad, "messages": []})
        assert out["error"] and out["pending_approval"] is None
    resolved = await resolve_approval_node({"pending_approval": {"tool_name": "rm_rf"}, "user_input": "승인", "messages": []})
    assert resolved["approval_decision"] == "rejected" and resolved["pending_approval"] is None
