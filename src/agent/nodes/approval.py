# approval 노드: 승인 대상 툴(REQUIRES_APPROVAL) 호출이 있으면 interrupt()로 멈춘다.
# resume 값 {"approved": bool}로 재개되며, 거절 시 ToolMessage를 달아 agent로 돌려보낸다.
# interrupt payload 형식은 FastAPI/UI와의 계약이라 고정한다 (CLAUDE.md 5.5).

from agent.state import AgentState
from agent.tools.registry import REQUIRES_APPROVAL
from langchain_core.messages import ToolMessage
from langgraph.types import interrupt


async def approval_node(state: AgentState) -> dict:
    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", None) or []
    approval_targets = [tc for tc in tool_calls if tc["name"] in REQUIRES_APPROVAL]

    if not approval_targets:
        return {}

    decisions: dict[str, bool] = {}
    for tc in approval_targets:
        result = interrupt(
            {
                "type": "approval_request",
                "tool": tc["name"],
                "args": tc["args"],
                "message": f"'{tc['name']}' 실행 전 승인이 필요합니다. 인자: {tc['args']}",
            }
        )
        decisions[tc["id"]] = bool(result.get("approved"))

    if all(decisions.values()):
        return {}  # 전부 승인 -> tools로 진행 (route_after_approval이 처리)

    # 하나라도 거절되면 이번 턴의 tool_call 전체를 취소하고 ToolNode를 건너뛴 채 agent로 돌아간다.
    # (한 AIMessage에 승인 대상 tool_call이 여러 개 섞여 일부만 승인되는 경우까지는 다루지 않는 예제 범위)
    reject_messages = [
        ToolMessage(
            content=(
                "사용자가 실행을 거절했습니다."
                if not decisions.get(tc["id"], True)
                else "다른 요청이 거절되어 함께 취소되었습니다."
            ),
            tool_call_id=tc["id"],
        )
        for tc in tool_calls
    ]
    return {"messages": reject_messages}
