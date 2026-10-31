"""PKU periods and date-based semester boundaries from the school calendar."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import re
import unicodedata

BEIJING = dt.timezone(dt.timedelta(hours=8))
PERIODS = [
    (1, "08:00", "08:50"), (2, "09:00", "09:50"),
    (3, "10:10", "11:00"), (4, "11:10", "12:00"),
    (5, "13:00", "13:50"), (6, "14:00", "14:50"),
    (7, "15:10", "16:00"), (8, "16:10", "17:00"),
    (9, "17:10", "18:00"), (10, "18:40", "19:30"),
    (11, "19:40", "20:30"), (12, "20:40", "21:30"),
]
UNKNOWN_TERM = "unknown"
CALENDAR = json.loads((Path(__file__).parent / "semesters.json").read_text(encoding="utf-8"))


def validate_calendar(calendar=CALENDAR):
    windows = []
    ids = set()
    for entry in calendar["semesters"]:
        start, end = dt.date.fromisoformat(entry["start"]), dt.date.fromisoformat(entry["end"])
        if end < start or entry["id"] in ids:
            raise ValueError("学期起止日期或 ID 无效。")
        ids.add(entry["id"])
        windows.append((start, end))
    windows.sort()
    if any(a[1] >= b[0] for a, b in zip(windows, windows[1:])):
        raise ValueError("学期日期范围不能重叠。")


validate_calendar()


def semester_for_date(day):
    for entry in CALENDAR["semesters"]:
        if dt.date.fromisoformat(entry["start"]) <= day <= dt.date.fromisoformat(entry["end"]):
            return {"term_id": entry["id"], "term_label": entry["label"], "term_order": entry["order"]}
    return {"term_id": UNKNOWN_TERM, "term_label": "非教学期／校历待配置", "term_order": 0}


def today():
    return dt.datetime.now(BEIJING).date()


def normalized_text(value):
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def room_parts(value):
    raw = normalized_text(value)
    # Match both original and punctuation/space variants of placeholder locations.
    compact = re.sub(r"[\s\-—_·/]+", "", raw)
    if not compact or "默认教学楼" in compact or "默认教室" in compact:
        return None
    display = raw.removeprefix("北京大学本部").strip(" -")
    display = re.sub(r"\s+", "", display).replace("—", "-")
    building, separator, number = display.rpartition("-")
    if not separator:
        building, number = display, ""
    return {"room": display, "room_raw": raw, "building": building, "room_number": number}


def parse_periods(title):
    text = normalized_text(title)
    match = re.search(r"第\s*(\d{1,2})\s*(?:[-~—–至]\s*(\d{1,2})\s*)?(?:节|$)", text)
    if not match:
        return []
    start, end = int(match[1]), int(match[2] or match[1])
    return list(range(start, end + 1)) if 1 <= start <= end <= 12 else []


def normalize_lesson(row, date=None, term_label=None):
    place = room_parts(row.get("room", row.get("room_name")))
    if not place:
        return None, "placeholder_room"
    title = row.get("lesson_title", row.get("lessonTitle", row.get("sub_title", "")))
    periods = parse_periods(title)
    if not periods:
        return None, "unrecognized_period"
    day = date or row.get("lesson_date", row.get("date"))
    if isinstance(day, str):
        day = dt.date.fromisoformat(day)
    if not isinstance(day, dt.date):
        return None, "invalid_date"
    cid = str(row.get("course_id", row.get("courseId", row.get("id", ""))) or "")
    sid = str(row.get("sub_id", row.get("subId", "")) or "")
    if not cid or not sid:
        return None, "missing_id"
    label = term_label if term_label is not None else row.get("semester")
    return {
        **place, **semester_for_date(day), "semester_raw": str(label or ""),
        "course_id": cid, "sub_id": sid, "lesson_date": day,
        "title": str(row.get("title") or "课程名称待补充"),
        "teacher": str(row.get("teacher", row.get("lecturer_name", "")) or ""),
        "department": str(row.get("department") or ""),
        "lesson_title": title, "periods": periods,
        "source": "zhiyun",
    }, None


def clock(value):
    if not re.fullmatch(r"\d{2}:\d{2}", value or ""):
        raise ValueError("时间请使用 HH:MM 格式。")
    return dt.time.fromisoformat(value)


def parse_filters(query):
    day = dt.date.fromisoformat(query.get("date") or today().isoformat())
    mode = query.get("mode", "all")
    if mode not in ("all", "period", "time", "range"):
        raise ValueError("不支持的时段类型。")
    result = {"date": day, "term": query.get("term", ""), "building": query.get("building", ""),
              "room": normalized_text(query.get("room", "")), "mode": mode}
    if any(len(str(result[k])) > 120 for k in ("term", "building", "room")):
        raise ValueError("筛选内容过长。")
    if mode == "period":
        start = int(query.get("period_from", "1"))
        end = int(query.get("period_to", str(start)))
        if not 1 <= start <= end <= 12:
            raise ValueError("节次范围须在第 1–12 节之间，结束节次不能早于开始。")
        result["periods"] = list(range(start, end + 1))
    elif mode == "time":
        result["time"] = clock(query.get("time", ""))
    elif mode == "range":
        start, end = clock(query.get("start", "")), clock(query.get("end", ""))
        if end <= start:
            raise ValueError("结束时间须晚于开始时间；暂不支持跨天查询。")
        result.update(start=start, end=end)
    result["page"] = int(query.get("page", "1"))
    if not 1 <= result["page"] <= 10000:
        raise ValueError("页码无效。")
    return result
