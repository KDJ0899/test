# error 노드: state.error를 사용자용 안내 메시지(answer)로 바꿔 종료한다.
# Tool 호출 직후 실패했다면 AI 메시지의 tool_calls에 대응하는 ToolMessage가 없어 다음 턴 LLM 호출이 깨지므로,
# 응답 없는 tool_call에 실패 ToolMessage를 채워 이력을 정상 상태로 되돌린다.

from teams.team5.prompts import ERROR_TEMPLATE
from teams.team5.state import MyState
from langchain_core.messages import AIMessage, ToolMessage


async def error_node(state: MyState) -> dict:
    messages = state.get("messages", [])
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    stubs = [
        ToolMessage(content="실행하지 못했다 (오류).", tool_call_id=tc["id"])
        for m in messages
        if isinstance(m, AIMessage)
        for tc in m.tool_calls
        if tc["id"] not in answered
    ]
    answer = ERROR_TEMPLATE.format(error=state.get("error"))
    return {"messages": [*stubs, AIMessage(content=answer)], "answer": answer}
