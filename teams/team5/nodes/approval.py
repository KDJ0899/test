# HITL(대화형 승인) 노드 모음. interrupt()를 쓰지 않고 승인 대기 정보를 State(pending_approval)에 저장한 채 턴을 끝낸다.
#   request_approval  : 승인 대상 Tool 호출을 실행하지 않고 pending_approval에 기록 + 승인 요청 문구를 answer로 내보냄
#   resolve_approval  : 다음 턴 입력("승인"/"거절")을 판정. 모호하면 unclear
#   ask_approval_again: 모호한 답/다른 요청이 오면 실행하지 않고 같은 요청을 다시 묻는다 (오래된 승인 자동 실행 방지)
#   execute_approved_tool: 승인된 Tool을 State에 저장된 인자 그대로 직접 호출한다 (LLM이 인자를 다시 만들지 않는다).
#     ToolNode는 직전 AIMessage의 tool_calls에 의존하는데 승인은 턴을 건너 실행되므로, 여기서는 레지스트리의 허용된 Tool만 직접 호출한다.

import json
import re
import uuid
from datetime import datetime

from teams.team5.prompts import (
    APPROVAL_AGAIN_TEMPLATE,
    APPROVAL_CALL_LINE_TEMPLATE,
    APPROVAL_PENDING_TOOL_MESSAGE,
    APPROVAL_REJECTED_MESSAGE,
    APPROVAL_REQUEST_HEADER,
    APPROVAL_REQUEST_TEMPLATE,
    APPROVED_TOOL_FAILED_TEMPLATE,
    NO_PLAN_TO_SAVE_MESSAGE,
    SAVE_DONE_TEMPLATE,
)
from teams.team5.state import MyState
from teams.team5.tools.registry import REQUIRES_APPROVAL, get_tool
from langchain_core.messages import AIMessage, ToolMessage

AFFIRMATIVE_WORDS = {"예", "네", "넵", "응", "그래", "승인", "진행", "허용", "확인", "y", "yes", "ok", "okay"}
NEGATIVE_WORDS = {"아니오", "아니요", "아니", "아뇨", "거절", "취소", "싫어", "n", "no"}
ARGS_PREVIEW_CHARS = 300


def _normalize(text: str) -> str:
    return re.sub(r"[\s.!~]+", "", text).lower()


def is_affirmative(text: str) -> bool:
    return _normalize(text) in AFFIRMATIVE_WORDS


def is_negative(text: str) -> bool:
    return _normalize(text) in NEGATIVE_WORDS


def format_request(pending: dict) -> str:
    """승인 요청 문구. 인자가 길면(일정 전체 등) 앞부분만 보여준다. 실행에는 pending의 원본 인자를 쓴다."""
    args = json.dumps(pending["arguments"], ensure_ascii=False, sort_keys=True)
    if len(args) > ARGS_PREVIEW_CHARS:
        args = args[:ARGS_PREVIEW_CHARS] + "…"
    line = APPROVAL_CALL_LINE_TEMPLATE.format(name=pending["tool_name"], args=args)
    return APPROVAL_REQUEST_TEMPLATE.format(header=APPROVAL_REQUEST_HEADER, calls=line)


def _is_valid(pending: dict | None) -> bool:
    """저장된 승인 정보가 온전하고 허용된 Tool을 가리키는지 확인한다 (임의 Tool 이름 실행 방지)."""
    return bool(
        pending
        and pending.get("approval_id")
        and isinstance(pending.get("arguments"), dict)
        and pending.get("tool_name") in REQUIRES_APPROVAL
        and get_tool(pending["tool_name"]) is not None
    )


async def request_approval_node(state: MyState) -> dict:
    last_message = state["messages"][-1]
    calls = last_message.tool_calls
    # 응답 없는 tool_call이 이력에 남으면 다음 LLM 호출이 깨지므로, 이번 묶음 전체에 "실행 안 됨" ToolMessage를 채운다.
    placeholders = [
        ToolMessage(content=APPROVAL_PENDING_TOOL_MESSAGE, tool_call_id=c["id"], name=c["name"]) for c in calls
    ]
    target = next(c for c in calls if c["name"] in REQUIRES_APPROVAL)

    arguments = target["args"]
    if target["name"] == "save_trip_plan":
        # 저장할 일정은 LLM이 쓴 인자가 아니라 State의 trip_plan으로 고정한다.
        if not state.get("trip_plan"):
            return {"messages": [*placeholders, AIMessage(content=NO_PLAN_TO_SAVE_MESSAGE)], "answer": NO_PLAN_TO_SAVE_MESSAGE}
        arguments = {"trip_plan": state["trip_plan"]}

    pending = {
        "approval_id": uuid.uuid4().hex,
        "tool_name": target["name"],
        "arguments": arguments,
        "requested_at": datetime.now().isoformat(timespec="seconds"),
    }
    answer = format_request(pending)
    return {
        "messages": [*placeholders, AIMessage(content=answer)],
        "pending_approval": pending,
        "answer": answer,
    }


async def resolve_approval_node(state: MyState) -> dict:
    pending = state.get("pending_approval")
    if not _is_valid(pending):
        # 깨졌거나 허용되지 않은 승인 정보는 실행하지 않고 버린다.
        message = "유효하지 않은 승인 요청이라 취소했습니다."
        return {"pending_approval": None, "approval_decision": "rejected", "messages": [AIMessage(content=message)]}

    reply = state.get("user_input", "")
    if is_affirmative(reply):
        # 승인 후 재개되는 흐름의 intent를 정한다: 여행 계획 중이면 trip(툴 바인딩 유지), 아니면 qa.
        intent = "trip" if state.get("trip_status") in ("searching", "selecting", "planning") else "qa"
        return {"approval_decision": "approved", "intent": intent}
    if is_negative(reply):
        message = APPROVAL_REJECTED_MESSAGE.format(name=pending["tool_name"])
        return {"pending_approval": None, "approval_decision": "rejected", "messages": [AIMessage(content=message)]}
    return {"approval_decision": "unclear"}


async def ask_approval_again_node(state: MyState) -> dict:
    answer = APPROVAL_AGAIN_TEMPLATE.format(request=format_request(state["pending_approval"]))
    return {"messages": [AIMessage(content=answer)], "answer": answer}


async def execute_approved_tool_node(state: MyState) -> dict:
    pending = state.get("pending_approval")
    tool = get_tool(pending["tool_name"]) if _is_valid(pending) else None
    if tool is None:
        return {"pending_approval": None, "error": "승인된 Tool을 실행할 수 없습니다."}

    name, arguments = pending["tool_name"], pending["arguments"]
    call_id = f"approved-{pending['approval_id']}"
    try:
        result = await tool.ainvoke(arguments)  # State에 저장된 인자 그대로 실행
    except Exception as exc:
        result = json.dumps({"status": "error", "source": name, "data": None, "error": str(exc)}, ensure_ascii=False)

    # 이력에는 "AI가 Tool을 호출 -> 결과" 쌍으로 남겨 LLM이 일반 Tool 호출과 똑같이 읽게 한다.
    messages = [
        AIMessage(content="", tool_calls=[{"name": name, "args": arguments, "id": call_id, "type": "tool_call"}]),
        ToolMessage(content=result, tool_call_id=call_id, name=name),
    ]
    changes: dict = {"pending_approval": None, "messages": messages}  # pending 초기화: 같은 승인은 다시 실행되지 않는다.

    if name == "save_trip_plan":
        parsed = json.loads(result)
        if parsed["status"] == "ok":
            text = SAVE_DONE_TEMPLATE.format(**parsed["data"])
        else:
            text = APPROVED_TOOL_FAILED_TEMPLATE.format(name=name, error=parsed.get("error"))
        changes["messages"] = [*messages, AIMessage(content=text)]
    return changes
