"""Reuse the project's normal authenticated daily catalog endpoint."""
from __future__ import annotations

import datetime as dt
from .client import api_get
from .auth import acquire_token
from . import store


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
                    "department": course.get("kkxy_name") or course.get("structure_name") or "",
                }
    return list(rows.values())


def sync_day(day, progress=None):
    progress = progress or (lambda message: None)
    progress("正在读取当日全校课程目录")
    rows = fetch_day(day)
    progress("正在事务中更新 PostgreSQL")
    return store.save_day(day, rows)
