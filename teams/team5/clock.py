# 기준 날짜를 한 곳에서 꺼내는 모듈. "다음 달", "이번 주" 같은 상대 날짜의 기준이 되며,
# config.TODAY_OVERRIDE나 테스트의 monkeypatch로 고정할 수 있어 날짜 경계에서 테스트가 깨지지 않는다.

from datetime import date, datetime

from teams.team5 import config

WEEKDAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]


def today() -> date:
    if config.TODAY_OVERRIDE:
        return date.fromisoformat(config.TODAY_OVERRIDE)
    return datetime.now().date()


def today_label() -> str:
    """프롬프트에 넣을 '2026-10-16 (금요일)' 형태의 문자열."""
    d = today()
    return f"{d.isoformat()} ({WEEKDAY_NAMES[d.weekday()]}요일)"
