# 여행 일정 검증 함수. LLM이 만든 일정이 규칙을 지키는지 코드로 검사한다 (LLM 호출 없음, 순수 함수).
# 검사 항목: 선택 경기 누락, 경기 시작 시각 불일치, 시간 역전, 시간 겹침, 활동 중복, 여행 범위 이탈, 없는 장소 ID.
# 위반 목록(list[str])을 돌려주고, 비어 있으면 통과다. plan_trip 노드가 실패 시 다시 만들게 하는 근거로 쓴다.
# repair_items는 검증 전에 LLM 초안의 흔한 실수(없는 장소 ID, 중복, 시간 역전, 겹침)를 코드로 먼저 고친다 (사용자에게 되묻지 않기 위해).

from datetime import date, datetime, timedelta
from difflib import get_close_matches


def _parse(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def validate_trip_plan(
    plan: dict,
    selected_event: dict | None,
    duration_days: int | None = None,
    known_place_ids: set[str] | None = None,
    start_date: date | None = None,
) -> list[str]:
    errors: list[str] = []
    if not selected_event:
        return ["선택한 경기가 없다."]

    items = plan.get("items") or []
    event_start = _parse(selected_event["start_at"])
    event_date: date = event_start.date()
    first_date: date = start_date or event_date  # 여행 시작일이 따로 없으면 경기일을 Day 1로 본다.
    if duration_days and not (0 <= (event_date - first_date).days < duration_days):
        errors.append(f"경기일({event_date})이 여행 기간({first_date}부터 {duration_days}일)에 들어가지 않는다.")

    # 선택 경기 누락 / 경기 시작 시각 불일치
    event_items = [i for i in items if i.get("event_id") == selected_event["id"]]
    if not event_items:
        errors.append(f"선택 경기({selected_event['id']}) 항목이 일정에 없다.")
    for item in event_items:
        if _parse(item.get("start_at")) != event_start:
            errors.append(f"경기 항목의 시작 시각이 경기 시작 시각({selected_event['start_at']})과 다르다.")

    parsed: list[tuple[datetime, datetime, dict]] = []
    for item in items:
        start, end = _parse(item.get("start_at")), _parse(item.get("end_at"))
        name = item.get("activity", "?")
        if not start or not end:
            errors.append(f"'{name}'의 시각 형식이 잘못됐다.")
            continue
        if start >= end:
            errors.append(f"'{name}'의 시작 시각이 종료 시각보다 늦거나 같다 (시간 역전).")
        day = item.get("day")
        if duration_days and not (isinstance(day, int) and 1 <= day <= duration_days):
            errors.append(f"'{name}'의 day({day})가 여행 기간(1~{duration_days}일)을 벗어났다.")
        elif isinstance(day, int) and start.date() != first_date + timedelta(days=day - 1):
            errors.append(f"'{name}'의 날짜({start.date()})가 Day {day}와 맞지 않는다. Day 1은 {first_date}이다.")
        parsed.append((start, end, item))

    # 같은 날 항목끼리 시간이 겹치면 충돌
    parsed.sort(key=lambda p: p[0])
    for (s1, e1, a), (s2, e2, b) in zip(parsed, parsed[1:]):
        if s1.date() == s2.date() and s2 < e1:
            errors.append(f"'{a.get('activity')}'와 '{b.get('activity')}'의 시간이 겹친다.")

    # 활동 중복: 같은 장소를 두 번 넣었거나 같은 날 같은 활동명이 반복
    place_ids = [i["place_id"] for i in items if i.get("place_id")]
    for pid in sorted({p for p in place_ids if place_ids.count(p) > 1}):
        errors.append(f"장소 {pid}가 중복되어 있다.")
    if known_place_ids is not None:
        for pid in sorted({p for p in place_ids if p not in known_place_ids}):
            errors.append(f"검색 결과에 없는 장소 ID({pid})를 사용했다.")
    keys = [(i.get("day"), i.get("activity")) for i in items]
    for key in sorted({k for k in keys if keys.count(k) > 1}, key=str):
        errors.append(f"Day {key[0]}에 같은 활동('{key[1]}')이 중복되어 있다.")
    return errors


def repair_items(items: list[dict], event: dict, known_place_ids: set[str]) -> list[dict]:
    """LLM 초안 항목의 고칠 수 있는 실수를 코드로 고친다 (순수 함수).
    없는 장소 ID는 거의 같은 실제 ID로 바꾸고(없으면 ID만 비우고 '확인 필요'로 표시), 중복 장소/활동은 뒤의 것을 지우고,
    시간 역전은 바로잡고, 같은 날 겹침은 경기 항목은 고정한 채 다른 항목을 뒤로 밀거나 줄인다. 고칠 수 없는 문제(날짜/Day 불일치)는 검증이 다시 잡는다."""
    event_start = _parse(event["start_at"])
    seen_places: set[str] = set()
    seen_activities: set[tuple] = set()
    rows: list[list] = []  # [start, end, item]
    for raw in items:
        item = dict(raw)
        is_event = item.get("event_id") == event["id"]
        pid = item.get("place_id")
        if pid and pid not in known_place_ids:
            close = get_close_matches(pid, known_place_ids, n=1, cutoff=0.75)  # 오타/접두어 수준만 같은 장소로 본다.
            item["place_id"] = pid = close[0] if close else None
            if not close:
                item["notes"] = "장소 정보 확인 필요" if not item.get("notes") else item["notes"] + " (장소 정보 확인 필요)"
        key = (item.get("day"), item.get("activity"))
        if (pid and pid in seen_places) or key in seen_activities:
            continue
        seen_places.add(pid) if pid else None
        seen_activities.add(key)
        start, end = _parse(item.get("start_at")), _parse(item.get("end_at"))
        if not start or not end:
            rows.append([None, None, item])  # 형식 오류는 고치지 않고 검증이 알린다.
            continue
        if is_event and event_start:
            start = event_start
        if start > end:
            start, end = (start, start + timedelta(hours=3)) if is_event else (end, start)
        elif start == end:
            end = start + timedelta(hours=3 if is_event else 1)
        rows.append([start, end, item])

    broken = [r for r in rows if r[0] is None]
    timed = sorted((r for r in rows if r[0] is not None), key=lambda r: r[0])
    result: list[list] = []
    for row in timed:
        is_event = row[2].get("event_id") == event["id"]
        while result and result[-1][0].date() == row[0].date() and row[0] < result[-1][1]:
            prev = result[-1]
            if is_event:
                if prev[0] >= row[0]:
                    result.pop()  # 경기 시작 이후에 시작하는 항목은 뺀다 (경기 시각은 고정).
                    continue
                prev[1] = row[0]  # 경기 직전 항목은 경기 시작에 맞춰 줄인다.
            else:
                length = row[1] - row[0]
                row[0] = prev[1]
                row[1] = row[0] + length
            break
        result.append(row)
    for start, end, item in [*result, *broken]:
        if start:
            item["start_at"], item["end_at"] = start.isoformat(), end.isoformat()
    return [r[2] for r in [*result, *broken]]
