"""Run: .venv/Scripts/python.exe -m unittest room_search.test_classroom -v"""
import datetime as dt
import http.server
import json
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from . import database, model, store, sync
from .server import Handler


def source(cid="1", sid="1", day="2026-10-21", title="第1-2节", room="北京大学本部理教-307", term=None):
    return {"course_id": cid, "sub_id": sid, "date": day, "lesson_title": title,
            "room": room, "title": "测试课程", "teacher": "教师", "semester": term}


class ModelTests(unittest.TestCase):
    def test_periods_and_placeholder_variants(self):
        self.assertEqual(model.parse_periods("2026-10-21第10-12节"), [10, 11, 12])
        self.assertEqual(model.parse_periods("第９节"), [9])
        self.assertEqual(model.parse_periods("2025-09-27第5-8"), [5,6,7,8])
        self.assertEqual(model.parse_periods("第12-13节"), [])
        self.assertEqual(model.parse_periods("第6-5节"), [])
        for room in ["默认校区默认教学楼-默认教室", "默认教学楼默认教室", " 默认教室 ", "", None]:
            self.assertIsNone(model.room_parts(room))
        self.assertEqual(model.room_parts("北京大学本部二教-210")["building"], "二教")

    def test_semesters_use_lesson_date_not_course_metadata(self):
        for day, expected in [("2025-09-08", "2025-2026-1"), ("2026-01-11", "2025-2026-1"),
                              ("2026-01-12", "unknown"), ("2026-03-02", "2025-2026-2"),
                              ("2026-07-05", "unknown"), ("2026-07-06", "2025-2026-3"),
                              ("2026-08-09", "2025-2026-3"), ("2026-08-10", "unknown"),
                              ("2026-09-07", "2026-2027-1"), ("2027-02-22", "2026-2027-2"),
                              ("2027-07-05", "2026-2027-3"), ("2027-08-08", "2026-2027-3"),
                              ("2027-08-09", "unknown")]:
            with self.subTest(day=day):
                item, reason = model.normalize_lesson(source(day=day, term="2023-2024 学年 · 第一学期"))
                self.assertIsNone(reason)
                self.assertEqual(item["term_id"], expected)
        bad = {"semesters": [{"id": "a", "start": "2026-01-01", "end": "2026-03-01"},
                              {"id": "b", "start": "2026-03-01", "end": "2026-04-01"}]}
        with self.assertRaises(ValueError):
            model.validate_calendar(bad)

    def test_filter_validation(self):
        for query in [{"mode":"range","start":"10:00","end":"09:00"}, {"mode":"period","period_from":"13"},
                      {"mode":"period","period_from":"4","period_to":"3"}, {"mode":"time","time":"25:00"},
                      {"date":"not-a-date"}, {"page":"0"}, {"mode":"invalid"}]:
            with self.subTest(query=query), self.assertRaises(ValueError):
                model.parse_filters(query)

    def test_child_location_overrides_course_location(self):
        payload = {"list":[{"list":[{"id":"1","title":"课程","room_name":"默认教室",
            "sub_list":[{"sub_id":"2","room_name":"北京大学本部二教-210","sub_title":"第3-4节"}]}]}]}
        with patch.object(sync, "api_get", return_value=payload), patch.object(sync, "acquire_token", return_value="test"):
            rows = sync.fetch_day(dt.date(2026,10,21))
        self.assertEqual(rows[0]["room"], "北京大学本部二教-210")

    def test_failed_sync_does_not_replace_existing_day(self):
        with patch.object(sync,"fetch_day",side_effect=RuntimeError("network error")), patch.object(store,"save_day") as save:
            with self.assertRaises(RuntimeError):
                sync.sync_day(dt.date(2026,10,21))
            save.assert_not_called()


class PostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "room_test_" + uuid.uuid4().hex
        cls.schema_patch = patch.object(store, "S", '"' + cls.schema + '"')
        cls.schema_patch.start()
        store.init_schema()
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1",0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        with database.connection() as conn:
            conn.execute('DROP SCHEMA "' + cls.schema + '" CASCADE')
        cls.schema_patch.stop()

    def setUp(self):
        with database.connection() as conn:
            conn.execute(f"DELETE FROM {store.S}.lessons")
            conn.execute(f"DELETE FROM {store.S}.days")
        self.day = dt.date(2026,10,21)
        store.save_day(self.day, [
            source(), source("2","2",title="第3-4节",room="北京大学本部二教-210"),
            source("3","3",room="默认教学楼-默认教室")])

    def search(self, **params):
        return store.search({"date":str(self.day), **params})

    def test_breaks_boundaries_and_ranges(self):
        for time, total in [("08:00",1), ("08:49",1), ("08:50",0), ("08:55",0),
                            ("09:00",1), ("09:50",0), ("10:10",1), ("12:00",0)]:
            with self.subTest(time=time):
                self.assertEqual(self.search(mode="time",time=time)["total"], total)
        self.assertEqual(self.search(mode="range",start="08:50",end="09:00")["total"],0)
        self.assertEqual(self.search(mode="range",start="08:49",end="09:01")["total"],1)
        self.assertEqual(self.search(mode="period",period_from="2",period_to="3")["total"],2)

    def test_default_discard_and_literal_search(self):
        result = self.search()
        self.assertEqual(result["total"],2)
        self.assertEqual(result["coverage"]["excluded"]["placeholder_room"],1)
        self.assertEqual(self.search(room="307")["total"],1)
        self.assertEqual(self.search(building="理教")["total"],1)
        self.assertEqual(self.search(room="%")["total"],0)
        self.assertEqual(self.search(room="' OR 1=1 --")["total"],0)

    def test_semester_isolation_and_empty_day_coverage(self):
        store.save_day(dt.date(2026,7,7),[source("1","1",day="2026-07-07")])
        result=store.search({"date":"2026-07-07","term":"2025-2026-3"})
        self.assertEqual(result["total"],1)
        self.assertEqual(result["lessons"][0]["semester"],"2025–2026 学年 · 夏季学期")
        self.assertEqual(self.search(term="2025-2026-3")["total"],0)
        self.assertIsNone(store.search({"date":"2026-10-22"})["coverage"])
        store.save_day(dt.date(2026,10,22),[])
        self.assertIsNotNone(store.search({"date":"2026-10-22"})["coverage"])

    def test_atomic_replacement_and_idempotence(self):
        store.save_day(self.day,[source()])
        self.assertEqual(self.search()["total"],1)
        store.save_day(self.day,[source()])
        self.assertEqual(self.search()["total"],1)
        with patch.object(store,"_write",side_effect=RuntimeError("transaction failure")):
            with self.assertRaises(RuntimeError):
                store.save_day(self.day,[])
        self.assertEqual(self.search()["total"],1)

    def test_http_search_and_origin_guard(self):
        base = "http://127.0.0.1:" + str(self.server.server_port)
        with urllib.request.urlopen(base + "/api/search?date=2026-10-21&mode=time&time=08:55") as res:
            self.assertEqual(json.load(res)["total"],0)
        request=urllib.request.Request(base + "/api/meta",headers={"Origin":"https://example.org"})
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request)
        self.assertEqual(raised.exception.code,403)
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(base + "/api/search?mode=period&period_from=99")
        self.assertEqual(raised.exception.code,400)

    def test_concurrent_schema_initialization(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: store.init_schema(), range(2)))
        self.assertEqual(self.search()["total"],2)

    def test_calendar_changes_reclassify_existing_rows(self):
        revised={"semesters":[{"id":"2026-2027-2","label":"按日期更新的春季学期",
                              "order":20262,"start":"2026-10-01","end":"2026-10-31"}]}
        with patch.object(model,"CALENDAR",revised):
            self.assertEqual(store.reclassify()["reclassified"],2)
        result=self.search(term="2026-2027-2")
        self.assertEqual(result["total"],2)
        self.assertEqual(result["lessons"][0]["semester"],"按日期更新的春季学期")


if __name__ == "__main__":
    unittest.main()
