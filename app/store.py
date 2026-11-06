"""SQLite event store. Thread-safe through one lock."""
import secrets
import sqlite3
import threading
import time

from . import config

_lock = threading.Lock()
_conn = None


def _db():
    global _conn
    if _conn is None:
        config.ensure_dirs()
        _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS events(
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                camera_id TEXT,
                camera_name TEXT,
                place TEXT,
                ts REAL NOT NULL,
                confidence REAL,
                status TEXT NOT NULL DEFAULT 'new',
                photo TEXT,
                clip TEXT,
                notice_at REAL)"""
        )
        _conn.execute("CREATE INDEX IF NOT EXISTS ev_ts ON events(ts DESC)")
        _conn.commit()
    return _conn


def new_id():
    return "E-" + time.strftime("%y%m%d") + "-" + secrets.token_hex(3).upper()


def add_event(**fields):
    with _lock:
        c = _db()
        cols = ",".join(fields)
        marks = ",".join("?" * len(fields))
        c.execute(f"INSERT INTO events({cols}) VALUES({marks})", list(fields.values()))
        c.commit()


def list_events(kind=None, status=None, q=None, limit=200):
    where, args = [], []
    if kind in ("litter", "spit"):
        where.append("kind=?")
        args.append(kind)
    if status == "open":
        where.append("status IN ('new','reviewed')")
    elif status in ("new", "reviewed", "noticed", "dismissed"):
        where.append("status=?")
        args.append(status)
    if q:
        like = f"%{q}%"
        where.append("(id LIKE ? OR place LIKE ? OR camera_name LIKE ?)")
        args += [like, like, like]
    sql = "SELECT * FROM events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY ts DESC LIMIT ?"
    args.append(limit)
    with _lock:
        return [dict(r) for r in _db().execute(sql, args).fetchall()]


def get_event(eid):
    with _lock:
        row = _db().execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
        return dict(row) if row else None


def update_event(eid, **fields):
    if not fields:
        return
    with _lock:
        c = _db()
        sets = ",".join(f"{k}=?" for k in fields)
        c.execute(f"UPDATE events SET {sets} WHERE id=?", [*fields.values(), eid])
        c.commit()


def counts():
    since = time.time() - 86400
    with _lock:
        rows = _db().execute(
            "SELECT kind, COUNT(*) AS n FROM events WHERE ts>=? GROUP BY kind", (since,)
        ).fetchall()
    return {r["kind"]: r["n"] for r in rows}
