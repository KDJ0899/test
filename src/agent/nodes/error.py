# error 노드: state.error를 사용자용 안내 메시지로 변환하고 종료한다.
# respond 노드와 동일하게 answer 키로 결과를 반환한다.

from agent.state import AgentState


async def error_node(state: AgentState) -> dict:
    return {"answer": f"요청을 처리하는 중 문제가 발생했습니다: {state.get('error')}"}
