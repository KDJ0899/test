# respond 노드: 마지막 AI 메시지를 최종 답변 문자열(answer)로 꺼내 State에 담는다.

from teams.team5.state import MyState


def respond_node(state: MyState) -> dict:
    return {"answer": str(state["messages"][-1].content)}
