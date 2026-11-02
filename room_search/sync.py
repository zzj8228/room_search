"""Reuse the project's normal authenticated daily catalog endpoint."""
from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
from .client import api_get
from .auth import AuthError, acquire_token
from .model import normalize_lesson
from . import store


def department_name(entry):
    for key in ("kkxy_name", "structure_name", "department"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def fetch_department(course_id):
    """Keep only the department string; never retain the raw schedule response."""
    data = api_get("schedule/search-live-course-list", {
        "all": 1, "course_id": course_id, "with_sub_data": 1, "with_room_data": 1,
    }, acquire_token())
    if not isinstance(data.get("list"), list):
        raise RuntimeError("课程排课接口格式异常，院系信息未更新。")
    names = {department_name(entry) for entry in data["list"]
             if isinstance(entry, dict) and str(entry.get("course_id") or entry.get("id") or "") == str(course_id)}
    names.discard("")
    return next(iter(names)) if len(names) == 1 else ""


def fetch_departments(course_ids, progress):
    departments, failed = {}, 0
    ids = sorted(set(course_ids))
    if not ids:
        return departments, failed
    progress(f"正在补全 {len(ids)} 门课程的院系")
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {pool.submit(fetch_department, cid): cid for cid in ids}
        for future in as_completed(pending):
            try:
                department = future.result()
            except (AuthError, RuntimeError):
                failed += 1
                continue
            if department:
                departments[pending[future]] = department
    return departments, failed


def fetch_day(day):
    data = api_get("course-live/search-live-course-list", {
        "need_time_quantum": 1, "unique_course": 1, "with_sub_duration": 1,
        "search_time": day.isoformat(), "tenant": 226, "course_student_type": "",
        "sub_live_status": "", "with_sub_data": 1,
    }, acquire_token())
    if not isinstance(data.get("list"), list) or data.get("has_more"):
        raise RuntimeError("目录结构不完整或存在未处理分页，本次未覆盖旧数据。")
    rows = {}
    for slot in data["list"]:
        if not isinstance(slot, dict) or not isinstance(slot.get("list"), list):
            raise RuntimeError("时段目录格式异常，本次未覆盖旧数据。")
        for course in slot["list"]:
            if not isinstance(course, dict):
                raise RuntimeError("课程记录格式异常，本次未覆盖旧数据。")
            nested = course.get("sub_list", course.get("sub_data"))
            if nested is not None and not isinstance(nested, list):
                raise RuntimeError("课次列表格式异常，本次未覆盖旧数据。")
            for lesson in nested if nested else [course]:
                cid = str(lesson.get("course_id", course.get("id", "")) or "")
                sid = str(lesson.get("sub_id", "") or "")
                if not cid or not sid:
                    raise RuntimeError("目录缺少课程或课次 ID，本次未覆盖旧数据。")
                # Child lesson location must override a parent course location.
                rows[(cid, sid)] = {
                    "course_id": cid, "sub_id": sid, "date": day.isoformat(),
                    "title": lesson.get("title") or course.get("title", ""),
                    "lesson_title": lesson.get("sub_title", ""),
                    "teacher": lesson.get("lecturer_name") or course.get("lecturer_name", ""),
                    "room": lesson.get("room_name", course.get("room_name", "")),
                    "department": department_name(lesson) or department_name(course),
                }
    return list(rows.values())


def sync_day(day, progress=None):
    progress = progress or (lambda message: None)
    progress("正在读取当日全校课程目录")
    rows = fetch_day(day)
    # Excluded placeholder rooms and invalid periods do not need course lookups.
    accepted = [row for row in rows if normalize_lesson(row, day)[1] is None]
    missing = {row["course_id"] for row in accepted if not row["department"]}
    known = store.known_departments(missing)
    fetched, failed = fetch_departments(missing - known.keys(), progress)
    departments = {**known, **fetched}
    for row in accepted:
        if not row["department"]:
            row["department"] = departments.get(row["course_id"], "")
    progress("正在事务中更新 PostgreSQL")
    result = store.save_day(day, rows)
    result["departments"] = {"cached_courses": len(known), "fetched_courses": len(fetched),
                             "failed_courses": failed,
                             "missing_lessons": sum(not row["department"] for row in accepted)}
    return result


def repair_departments(progress=None):
    """Repair existing lessons without replacing dates or copying replay metadata."""
    progress = progress or (lambda message: None)
    result = store.repair_departments()
    fetched, failed = fetch_departments(store.missing_department_courses(), progress)
    repaired = store.repair_departments(fetched)
    return {"updated": result["updated"] + repaired["updated"], "remaining": repaired["remaining"],
            "fetched_courses": len(fetched), "failed_courses": failed}
