"""PostgreSQL classroom data. Replay tables are read-only inputs."""
from __future__ import annotations

from collections import Counter
import json
import os
import re

from psycopg import sql
import psycopg
from psycopg.rows import dict_row
from . import database as db
from .model import PERIODS, normalize_lesson, parse_filters

SCHEMA = os.environ.get("PKU_ROOM_SCHEMA", "pku_room_search")
if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", SCHEMA):
    raise RuntimeError("教室数据库 schema 名称无效。")
S = '"' + SCHEMA + '"'
PAGE_SIZE = 60
COLUMNS = ("course_id", "sub_id", "lesson_date", "lesson_title", "title", "teacher", "department", "room",
           "room_raw", "building", "room_number", "periods", "term_id", "semester_raw", "source")


def init_schema():
    with db.connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("classroom-schema:" + SCHEMA,))
        conn.execute(f"""CREATE SCHEMA IF NOT EXISTS {S};
        CREATE TABLE IF NOT EXISTS {S}.terms (
            term_id text PRIMARY KEY, label text NOT NULL, sort_order integer NOT NULL
        );
        CREATE TABLE IF NOT EXISTS {S}.periods (
            number smallint PRIMARY KEY CHECK (number BETWEEN 1 AND 12),
            starts time NOT NULL, ends time NOT NULL CHECK (ends > starts)
        );
        CREATE TABLE IF NOT EXISTS {S}.lessons (
            course_id text NOT NULL, sub_id text NOT NULL, lesson_date date NOT NULL,
            lesson_title text NOT NULL, title text NOT NULL, teacher text NOT NULL, department text NOT NULL,
            room text NOT NULL CHECK (room <> '' AND room NOT LIKE '%%默认%%'),
            room_raw text NOT NULL, building text NOT NULL, room_number text NOT NULL,
            periods smallint[] NOT NULL CHECK (cardinality(periods)>0 AND periods <@ ARRAY[1,2,3,4,5,6,7,8,9,10,11,12]::smallint[]),
            term_id text NOT NULL REFERENCES {S}.terms(term_id), semester_raw text NOT NULL,
            source text NOT NULL, imported_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (source,course_id,sub_id,lesson_date)
        );
        CREATE INDEX IF NOT EXISTS lessons_date_term_room ON {S}.lessons(lesson_date,term_id,building,room);
        CREATE INDEX IF NOT EXISTS lessons_term_date ON {S}.lessons(term_id,lesson_date);
        ALTER TABLE {S}.lessons ADD COLUMN IF NOT EXISTS lesson_title text NOT NULL DEFAULT '';
        CREATE TABLE IF NOT EXISTS {S}.days (
            lesson_date date PRIMARY KEY, source text NOT NULL,
            raw_count integer NOT NULL, accepted_count integer NOT NULL,
            excluded jsonb NOT NULL, fetched_at timestamptz NOT NULL DEFAULT now()
        );""")
        with conn.cursor() as cur:
            cur.executemany(f"""INSERT INTO {S}.periods VALUES (%s,%s,%s)
                ON CONFLICT(number) DO UPDATE SET starts=EXCLUDED.starts,ends=EXCLUDED.ends""", PERIODS)


def _write(conn, normalized):
    terms = {row["term_id"]: row for row in normalized}
    with conn.cursor() as cur:
        cur.executemany(f"""INSERT INTO {S}.terms VALUES (%s,%s,%s)
            ON CONFLICT(term_id) DO UPDATE SET label=EXCLUDED.label,sort_order=EXCLUDED.sort_order""",
            [(x["term_id"], x["term_label"], x["term_order"]) for x in terms.values()])
    conn.execute(f"CREATE TEMP TABLE incoming (LIKE {S}.lessons INCLUDING DEFAULTS) ON COMMIT DROP")
    copy_sql = sql.SQL("COPY incoming ({}) FROM STDIN").format(sql.SQL(",").join(map(sql.Identifier, COLUMNS)))
    with conn.cursor().copy(copy_sql) as copy:
        for row in normalized:
            copy.write_row(tuple(row[k] for k in COLUMNS))
    cols = ",".join(COLUMNS)
    updates = ",".join(k + "=EXCLUDED." + k for k in COLUMNS if k not in ("source", "course_id", "sub_id", "lesson_date"))
    conn.execute(f"""INSERT INTO {S}.lessons ({cols}) SELECT {cols} FROM incoming
        ON CONFLICT(source,course_id,sub_id,lesson_date) DO UPDATE SET {updates},imported_at=now()""")
    conn.execute("DROP TABLE incoming")


def save_day(day, rows, term_labels=None, source="zhiyun"):
    normalized, excluded = {}, Counter()
    for row in rows:
        cid = str(row.get("courseId", row.get("id", row.get("course_id", ""))))
        # Kept only as provenance; the date calendar always determines the semester.
        label = (term_labels or {}).get(cid)
        item, reason = normalize_lesson(row, day, label)
        if reason:
            excluded[reason] += 1
        else:
            normalized[(item["course_id"], item["sub_id"])] = item
    values = list(normalized.values())
    with db.connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("classroom-data:" + SCHEMA,))
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("pku-room-day:" + str(day),))
        # An authoritative, successful day replaces its previous classroom snapshot atomically.
        conn.execute(f"DELETE FROM {S}.lessons WHERE lesson_date=%s AND source='zhiyun'", (day,))
        _write(conn, values)
        conn.execute(f"""INSERT INTO {S}.days(lesson_date,source,raw_count,accepted_count,excluded)
            VALUES (%s,%s,%s,%s,%s::jsonb) ON CONFLICT(lesson_date) DO UPDATE SET
            source=EXCLUDED.source,raw_count=EXCLUDED.raw_count,accepted_count=EXCLUDED.accepted_count,
            excluded=EXCLUDED.excluded,fetched_at=now()""",
            (day, source, len(rows), len(values), json.dumps(dict(excluded))))
    return {"date": str(day), "raw": len(rows), "accepted": len(values), "excluded": dict(excluded)}


def import_existing():
    """Stream the local replay catalog; no remote requests, no replay mutations."""
    from .model import normalize_lesson
    counts, per_day = Counter(), {}
    from .model import CALENDAR
    first = min(entry["start"] for entry in CALENDAR["semesters"])
    with psycopg.connect(db.source_connection_url(), connect_timeout=5, row_factory=dict_row) as reader, db.connection() as writer:
        if reader.info.dbname == writer.info.dbname and reader.info.host == writer.info.host and reader.info.port == writer.info.port:
            raise ValueError("导入源与目标必须是不同数据库。")
        reader.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        writer.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("classroom-data:" + SCHEMA,))
        covered = reader.execute("SELECT lesson_date FROM pku_catalog_days WHERE lesson_date >= %s", (first,)).fetchall()
        # Build a full staging snapshot first. Failure leaves the previous dataset intact.
        writer.execute(f"CREATE TEMP TABLE migration_rows (LIKE {S}.lessons INCLUDING DEFAULTS) ON COMMIT DROP")
        terms = {}
        copy_sql = sql.SQL("COPY migration_rows ({}) FROM STDIN").format(sql.SQL(",").join(map(sql.Identifier, COLUMNS)))
        with reader.cursor(name="room_catalog_input") as cursor, writer.cursor().copy(copy_sql) as copy:
            cursor.execute("""SELECT l.course_id,l.sub_id,l.lesson_date,l.lesson_title,l.room,
                c.title,c.teacher,c.department FROM pku_lessons l JOIN pku_courses c USING(course_id)
                WHERE l.lesson_date >= %s""", (first,))
            for row in cursor:
                day = row["lesson_date"]
                audit = per_day.setdefault(day, {"raw": 0, "accepted": 0, "excluded": Counter()})
                audit["raw"] += 1
                item, reason = normalize_lesson(row)
                if reason:
                    counts[reason] += 1
                    audit["excluded"][reason] += 1
                    continue
                terms[item["term_id"]] = item
                counts["accepted"] += 1
                audit["accepted"] += 1
                copy.write_row(tuple(item[k] for k in COLUMNS))
        with writer.cursor() as cur:
            cur.executemany(f"""INSERT INTO {S}.terms VALUES (%s,%s,%s)
                ON CONFLICT(term_id) DO UPDATE SET label=EXCLUDED.label,sort_order=EXCLUDED.sort_order""",
                [(t["term_id"], t["term_label"], t["term_order"]) for t in terms.values()])
        # Copying the catalog is a bootstrap. Already synchronized days stay authoritative.
        writer.execute(f"""DELETE FROM {S}.lessons l USING {S}.days d
            WHERE l.lesson_date=d.lesson_date AND d.source='existing_catalog'""")
        cols = ",".join(COLUMNS)
        writer.execute(f"""INSERT INTO {S}.lessons ({cols}) SELECT {cols} FROM migration_rows r
            WHERE NOT EXISTS (SELECT 1 FROM {S}.days d WHERE d.lesson_date=r.lesson_date AND d.source<>'existing_catalog')
            ON CONFLICT DO NOTHING""")
        with writer.cursor() as cur:
            audits = []
            for day in set(per_day) | {r["lesson_date"] for r in covered}:
                a = per_day.get(day, {"raw": 0, "accepted": 0, "excluded": {}})
                audits.append((day, a["raw"], a["accepted"], json.dumps(dict(a["excluded"]))))
            cur.executemany(f"""INSERT INTO {S}.days(lesson_date,source,raw_count,accepted_count,excluded)
                VALUES (%s,'existing_catalog',%s,%s,%s::jsonb) ON CONFLICT(lesson_date) DO UPDATE SET
                raw_count=EXCLUDED.raw_count,accepted_count=EXCLUDED.accepted_count,excluded=EXCLUDED.excluded,
                fetched_at=now() WHERE {S}.days.source='existing_catalog'""", audits)
    return dict(counts)


def reclassify():
    """Reapply a changed calendar to all lessons, including directly synced days."""
    from .model import CALENDAR
    with db.connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("classroom-data:" + SCHEMA,))
        entries = CALENDAR["semesters"]
        with conn.cursor() as cur:
            cur.executemany(f"""INSERT INTO {S}.terms VALUES (%s,%s,%s)
                ON CONFLICT(term_id) DO UPDATE SET label=EXCLUDED.label,sort_order=EXCLUDED.sort_order""",
                [("unknown", "非教学期／校历待配置", 0)] +
                [(r["id"],r["label"],r["order"]) for r in entries])
        clauses, params = [], []
        for row in entries:
            clauses.append("WHEN lesson_date BETWEEN %s AND %s THEN %s")
            params.extend([row["start"], row["end"], row["id"]])
        result = conn.execute(f"UPDATE {S}.lessons SET term_id=CASE " +
                              " ".join(clauses) + " ELSE 'unknown' END", params)
    return {"reclassified": result.rowcount, "basis": "lesson_date"}


def meta():
    with db.connection() as conn:
        terms = conn.execute(f"""SELECT t.term_id AS id,t.label,t.sort_order,count(*) AS lessons,
            min(l.lesson_date)::text AS first_date,max(l.lesson_date)::text AS last_date
            FROM {S}.lessons l JOIN {S}.terms t USING(term_id)
            GROUP BY t.term_id ORDER BY t.sort_order DESC""").fetchall()
        totals = conn.execute(f"""SELECT count(*) AS lessons,count(DISTINCT room) AS rooms,
            min(lesson_date)::text AS first_date,max(lesson_date)::text AS last_date,
            count(*) FILTER (WHERE term_id='unknown') AS unknown_terms FROM {S}.lessons""").fetchone()
        coverage = conn.execute(f"SELECT count(*) AS days,max(fetched_at) AS updated_at FROM {S}.days").fetchone()
    from .model import CALENDAR
    return {"terms": terms, "totals": totals, "coverage": coverage, "calendar": CALENDAR,
            "periods": [{"number": n, "start": a, "end": b} for n, a, b in PERIODS]}


def locations(term="", day=None):
    conditions, args = [], []
    if term:
        conditions.append("term_id=%s")
        args.append(term)
    # Per-semester locations remain available even when a selected date is missing.
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    with db.connection() as conn:
        rows = conn.execute(f"SELECT DISTINCT building,room FROM {S}.lessons" + where + " ORDER BY building,room", args).fetchall()
    return {"locations": rows}


def search(query):
    filters = parse_filters(query)
    conditions, args = ["l.lesson_date=%s"], [filters["date"]]
    if filters["term"]:
        conditions.append("l.term_id=%s")
        args.append(filters["term"])
    if filters["building"]:
        conditions.append("l.building=%s")
        args.append(filters["building"])
    if filters["room"]:
        text = filters["room"].replace("北京大学本部", "")
        # User input is a literal substring, not a LIKE wildcard.
        text = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append("l.room ILIKE %s ESCAPE E'\\\\'")
        args.append("%" + text + "%")
    if filters["mode"] == "period":
        conditions.append("l.periods && %s::smallint[]")
        args.append(filters["periods"])
    elif filters["mode"] in ("time", "range"):
        part = "p.starts<=%s AND p.ends>%s" if filters["mode"] == "time" else "p.starts<%s AND p.ends>%s"
        conditions.append(f"EXISTS(SELECT 1 FROM {S}.periods p WHERE p.number=ANY(l.periods) AND {part})")
        args += [filters["time"], filters["time"]] if filters["mode"] == "time" else [filters["end"], filters["start"]]
    where = " WHERE " + " AND ".join(conditions)
    with db.connection() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        conn.execute("SET LOCAL statement_timeout='8s'")
        total = conn.execute(f"SELECT count(*) AS n FROM {S}.lessons l" + where, args).fetchone()["n"]
        rows = conn.execute(f"""SELECT l.course_id,l.sub_id,l.title,l.teacher,l.department,l.lesson_date,
            l.room,l.building,l.room_number,l.periods,l.term_id,t.label AS semester,l.lesson_title,l.source,
            l.imported_at FROM {S}.lessons l JOIN {S}.terms t USING(term_id)""" + where +
            " ORDER BY l.room,l.periods[1],l.title,l.course_id,l.sub_id LIMIT %s OFFSET %s",
            [*args, PAGE_SIZE, (filters["page"]-1)*PAGE_SIZE]).fetchall()
        coverage = conn.execute(f"SELECT * FROM {S}.days WHERE lesson_date=%s", (filters["date"],)).fetchone()
        term_day = conn.execute(f"""SELECT t.term_id,t.label,count(*) AS lessons FROM {S}.lessons l
            JOIN {S}.terms t USING(term_id) WHERE l.lesson_date=%s GROUP BY t.term_id""", (filters["date"],)).fetchall()
    for row in rows:
        row["times"] = [{"number": n, "start": a, "end": b} for n, a, b in PERIODS if n in row["periods"]]
    return {"lessons": rows, "total": total, "page": filters["page"], "page_size": PAGE_SIZE,
            "coverage": coverage, "date_terms": term_day, "filters": filters}
