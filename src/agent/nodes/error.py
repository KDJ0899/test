# error 노드: state.error를 사용자용 안내 메시지로 변환하고 종료한다.

from agent.state import AgentState
from langchain_core.messages import AIMessage


async def error_node(state: AgentState) -> dict:
    message = f"요청을 처리하는 중 문제가 발생했습니다: {state.get('error')}"
    return {"messages": [AIMessage(content=message)]}
