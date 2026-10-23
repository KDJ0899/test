# save_session 노드: 턴을 끝내는 모든 경로(respond, error, 질문/승인 요청 노드)의 마지막에서 여행 상태를 보관소에 저장한다.
# 이 노드는 State를 바꾸지 않는다. 다음 턴 classify가 session.restore_session으로 이 값을 되살린다.

from teams.team5.session import save_session
from teams.team5.state import MyState


def save_session_node(state: MyState) -> dict:
    save_session(state)
    return {}
