# 그래프 전체에서 공유되는 State 정의.
# 체크포인터가 없고 호출자는 messages만 보낸다. 여행 상태(trip_preferences, sports_events, trip_plan ...)는
# session.py의 보관소에 저장되었다가 classify에서 복원되어 다음 턴으로 이어지고,
# 턴 단위 값(intent, missing_fields, retrieved_docs, error, answer)은 classify 노드가 매 턴 초기화한다.

from typing import Annotated, Any, Literal

from langchain_core.documents import Document
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class TripPreferences(TypedDict, total=False):
    sport_type: str  # 기본 baseball
    team: str  # 예: 롯데 자이언츠
    destination: str  # 경기장으로 추론 가능
    date_from: str  # YYYY-MM-DD, 검색 시작
    date_to: str  # YYYY-MM-DD, 검색 종료
    preferred_weekdays: list[int]  # 월=0 ... 일=6
    duration_days: int  # 1박2일 = 2
    travelers: int
    transport: str  # public_transit / car / unspecified
    budget_krw: int
    interests: list[str]


class MyState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]  # 대화 이력 (add_messages로 누적)
    user_input: str
    intent: Literal["chat", "trip", "qa"] | None
    needs_guide: bool  # classify의 판단: 가이드 문서 검색이 필요한 질문인가 (True면 agent 전에 retrieve 강제)
    trip_preferences: TripPreferences
    missing_fields: list[str]
    clarification_note: str | None  # 날짜가 모호/모순일 때 extract가 남기는 확인 질문
    sports_events: list[dict[str, Any]]  # 검색 캐시 (번호 = 리스트 순서 + 1)
    selected_event_id: str | None
    places: list[dict[str, Any]]
    restaurants: list[dict[str, Any]]
    trip_plan: dict[str, Any] | None
    pending_approval: dict[str, Any] | None
    approval_decision: Literal["approved", "rejected", "unclear"] | None
    processed_tool_call_ids: list[str]
    tool_iterations: int  # 이번 턴의 Tool 실행 횟수 (최대 반복 제한용)
    retrieved_docs: list[Document]
    trip_status: Literal["idle", "collecting", "searching", "selecting", "planning", "completed"]
    error: str | None
    answer: str

