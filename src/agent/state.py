# 그래프 전체에서 공유되는 State 정의.
# InMemorySaver 체크포인터가 thread_id 단위로 이 State를 턴 사이에 보존한다.
# 대화(messages)와 여행 상태(trip_preferences, sports_events, trip_plan ...)는 유지하고,
# 턴 단위 값(intent, missing_fields, retrieved_docs, error, answer)은 classify 노드가 매 턴 초기화한다.

from typing import Annotated, Any, Literal

from langchain_core.documents import Document
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import NotRequired, TypedDict


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


class InputState(TypedDict):
    # 체크포인터를 쓰는 CLI에서는 첫 호출부터 user_input만 보낸다. messages는 초기화/호환성 용도.
    user_input: str
    messages: NotRequired[list[AnyMessage]]


class AgentState(TypedDict, total=False):
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


class OutputState(TypedDict):
    # output_schema로 ainvoke 결과를 {"answer": str}로 제한한다. 체크포인터에는 내부 State 전체가 남는다.
    answer: str
