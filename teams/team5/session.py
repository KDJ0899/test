# 여행 상태 보관소. 호출자(UI/FastAPI)는 messages(이력)만 보내므로, 이력에 없는 여행 상태(조건, 후보 경기, 선택, 일정, 승인 대기)를
# 프로세스 안의 dict 하나에 보관했다가 다음 턴에 복원한다. 사용자가 1명인 로컬 환경 전용이다 (대화 ID가 없어 대화별 구분은 하지 않는다).
# UI의 "새 대화"는 이력을 비워서 보내므로, 이력이 비어 있으면 새 대화로 보고 보관소를 초기화한다.

import copy

from teams.team5.state import MyState

# 턴이 끝나도 유지할 State 키. intent, missing_fields, answer 같은 턴 단위 값은 classify가 매 턴 초기화하므로 제외한다.
PERSISTED_KEYS = (
    "trip_preferences",
    "sports_events",
    "selected_event_id",
    "place_choice",
    "places",
    "restaurants",
    "trip_plan",
    "trip_status",
    "pending_approval",
)

_session: dict = {}


def reset_session() -> None:
    _session.clear()


def save_session(state: MyState) -> None:
    """턴이 끝날 때 호출. 다음 턴이 같은 객체를 공유하지 않도록 복사해서 저장한다."""
    _session.clear()
    _session.update({key: copy.deepcopy(state[key]) for key in PERSISTED_KEYS if key in state})


def restore_session(state: MyState) -> dict:
    """classify 시작 시 호출. 이력(messages)이 비어 있으면 새 대화이므로 초기화하고,
    아니면 보관한 값 중 호출자가 직접 넘기지 않은 키만 돌려준다 (State 전체를 넘기는 호출자는 그 값이 우선)."""
    if not state.get("messages"):
        reset_session()
        return {}
    return {key: copy.deepcopy(value) for key, value in _session.items() if key not in state}
