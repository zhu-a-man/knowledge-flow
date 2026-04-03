import os
import sqlite3
from datetime import datetime
from contextlib import contextmanager

# ── 存储后端选择 ──────────────────────────────────────────────────────
# Railway 部署时自动注入 DATABASE_URL（PostgreSQL）
# 本地开发没有该变量时，自动降级为 SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras

# SQLite 本地路径（仅本地开发使用）
DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
DB_PATH = os.path.join(DATA_DIR, "knowledge_base.db")


# ── PostgreSQL 表结构 ──────────────────────────────────────────────
_PG_DDL = [
    """
    CREATE TABLE IF NOT EXISTS kb_entries (
        id              SERIAL PRIMARY KEY,
        url             TEXT NOT NULL DEFAULT '',
        title           TEXT NOT NULL DEFAULT '',
        platform        TEXT NOT NULL DEFAULT '',
        summary         TEXT NOT NULL DEFAULT '',
        topic           TEXT NOT NULL,
        dimension       TEXT NOT NULL,
        content_form    TEXT NOT NULL DEFAULT '',
        created_at      TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS kb_points (
        id          SERIAL PRIMARY KEY,
        entry_id    INTEGER NOT NULL REFERENCES kb_entries(id) ON DELETE CASCADE,
        point       TEXT NOT NULL
    )
    """,
    # 兼容已有表：如果 content_form 列不存在则添加
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'kb_entries' AND column_name = 'content_form'
        ) THEN
            ALTER TABLE kb_entries ADD COLUMN content_form TEXT NOT NULL DEFAULT '';
        END IF;
    END $$;
    """,
]

# ── SQLite 表结构 ──────────────────────────────────────────────────
_SQLITE_DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS kb_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT NOT NULL DEFAULT '',
    title           TEXT NOT NULL DEFAULT '',
    platform        TEXT NOT NULL DEFAULT '',
    summary         TEXT NOT NULL DEFAULT '',
    topic           TEXT NOT NULL,
    dimension       TEXT NOT NULL,
    content_form    TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kb_points (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id    INTEGER NOT NULL REFERENCES kb_entries(id) ON DELETE CASCADE,
    point       TEXT NOT NULL
);
"""


# ── 连接上下文管理器 ───────────────────────────────────────────────
@contextmanager
def _pg_conn():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            for stmt in _PG_DDL:
                cur.execute(stmt)
        conn.commit()
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def _sqlite_conn():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SQLITE_DDL)
    _migrate_v1(conn)
    _migrate_add_content_form(conn)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _conn():
    return _pg_conn() if USE_POSTGRES else _sqlite_conn()


def _to_entries_list(extracted: dict) -> list:
    if "entries" in extracted:
        return extracted["entries"]
    return [{
        "topic": extracted.get("topic", "未分类"),
        "dimension": extracted.get("dimension", "通用"),
        "content_form": extracted.get("content_form", ""),
        "key_points": extracted.get("key_points", []),
    }]


def _migrate_add_content_form(conn: sqlite3.Connection):
    """SQLite 迁移：为已有表添加 content_form 列"""
    columns = {info[1] for info in conn.execute("PRAGMA table_info(kb_entries)").fetchall()}
    if "content_form" not in columns:
        conn.execute("ALTER TABLE kb_entries ADD COLUMN content_form TEXT NOT NULL DEFAULT ''")
        conn.commit()


# ── SQLite 历史数据迁移（仅本地用）──────────────────────────────────
def _migrate_v1(conn: sqlite3.Connection):
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if "sources" not in tables:
        return
    if conn.execute("SELECT COUNT(*) FROM kb_entries").fetchone()[0] > 0:
        return

    old_sources = conn.execute(
        "SELECT topic, dimension, title, url, platform, summary, created_at FROM sources"
    ).fetchall()
    old_points = conn.execute("SELECT topic, dimension, point FROM points").fetchall()

    pts_by_td: dict = {}
    for p in old_points:
        key = (p["topic"], p["dimension"])
        pts_by_td.setdefault(key, []).append(p["point"])

    for s in old_sources:
        cur = conn.execute(
            "INSERT INTO kb_entries (url, title, platform, summary, topic, dimension, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (s["url"], s["title"], s["platform"], s["summary"],
             s["topic"], s["dimension"], s["created_at"]),
        )
        entry_id = cur.lastrowid
        for point in pts_by_td.pop((s["topic"], s["dimension"]), []):
            conn.execute(
                "INSERT INTO kb_points (entry_id, point) VALUES (?, ?)",
                (entry_id, point),
            )
    conn.commit()


# ── 核心 API ──────────────────────────────────────────────────────
def add_knowledge(extracted: dict, source_info: dict) -> dict:
    url = (source_info.get("url") or "").strip()
    title = source_info.get("title") or "未知标题"
    platform = source_info.get("platform") or ""
    summary = extracted.get("summary") or ""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    entries = _to_entries_list(extracted)

    if USE_POSTGRES:
        return _pg_add_knowledge(url, title, platform, summary, now, entries)
    return _sqlite_add_knowledge(url, title, platform, summary, now, entries)


def _pg_add_knowledge(url, title, platform, summary, now, entries) -> dict:
    with _pg_conn() as conn:
        is_update = False
        if url:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM kb_entries WHERE url = %s AND url != ''",
                    (url,),
                )
                if cur.fetchone()[0] > 0:
                    cur.execute(
                        "DELETE FROM kb_entries WHERE url = %s AND url != ''",
                        (url,),
                    )
                    is_update = True

        for entry in entries:
            topic = entry.get("topic") or "未分类"
            dimension = entry.get("dimension") or "通用"
            content_form = entry.get("content_form") or ""
            key_points = entry.get("key_points") or []

            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO kb_entries (url, title, platform, summary, topic, dimension, content_form, created_at)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (url, title, platform, summary, topic, dimension, content_form, now),
                )
                entry_id = cur.fetchone()[0]
                for point in key_points:
                    cur.execute(
                        "INSERT INTO kb_points (entry_id, point) VALUES (%s, %s)",
                        (entry_id, point),
                    )

    return _build_result(entries, title, is_update)


def _sqlite_add_knowledge(url, title, platform, summary, now, entries) -> dict:
    with _sqlite_conn() as conn:
        is_update = False
        if url:
            old = conn.execute(
                "SELECT COUNT(*) FROM kb_entries WHERE url = ? AND url != ''", (url,)
            ).fetchone()[0]
            if old > 0:
                conn.execute(
                    "DELETE FROM kb_entries WHERE url = ? AND url != ''", (url,)
                )
                is_update = True

        for entry in entries:
            topic = entry.get("topic") or "未分类"
            dimension = entry.get("dimension") or "通用"
            content_form = entry.get("content_form") or ""
            key_points = entry.get("key_points") or []

            cur = conn.execute(
                "INSERT INTO kb_entries (url, title, platform, summary, topic, dimension, content_form, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (url, title, platform, summary, topic, dimension, content_form, now),
            )
            entry_id = cur.lastrowid
            for point in key_points:
                conn.execute(
                    "INSERT INTO kb_points (entry_id, point) VALUES (?, ?)",
                    (entry_id, point),
                )

    return _build_result(entries, title, is_update)


def _build_result(entries: list, title: str, is_update: bool) -> dict:
    total_pts = sum(len(e.get("key_points") or []) for e in entries)
    n = len(entries)
    if is_update:
        msg = f"🔄 已更新「{title[:20]}」，重新分入 {n} 个主题"
    elif n == 1:
        t = entries[0].get("topic", "")
        d = entries[0].get("dimension", "")
        msg = f"✨ 已保存到「{t} › {d}」"
    else:
        topics_str = "、".join(e.get("topic", "") for e in entries[:3])
        if n > 3:
            topics_str += "…"
        msg = f"✨ 已按 {n} 个主题分类保存：{topics_str}"

    return {
        "message": msg,
        "entries": entries,
        "summary": "",
        "is_update": is_update,
        "total_points": total_pts,
    }


def get_all() -> dict:
    if USE_POSTGRES:
        return _pg_get_all()
    return _sqlite_get_all()


def _pg_get_all() -> dict:
    with _pg_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    e.id, e.topic, e.dimension, e.content_form,
                    e.url, e.title, e.summary, e.created_at,
                    p.point
                FROM kb_entries e
                LEFT JOIN kb_points p ON p.entry_id = e.id
                ORDER BY e.topic, e.dimension, e.created_at, p.id
            """)
            rows = cur.fetchall()

            cur.execute(
                "SELECT COUNT(DISTINCT COALESCE(NULLIF(url,''), id::text)) FROM kb_entries"
            )
            total_items = cur.fetchone()["count"]

    return _build_tree(rows, total_items)


def _sqlite_get_all() -> dict:
    with _sqlite_conn() as conn:
        rows = conn.execute("""
            SELECT
                e.id, e.topic, e.dimension, e.content_form,
                e.url, e.title, e.summary, e.created_at,
                p.point
            FROM kb_entries e
            LEFT JOIN kb_points p ON p.entry_id = e.id
            ORDER BY e.topic, e.dimension, e.created_at, p.id
        """).fetchall()

        total_items = conn.execute(
            "SELECT COUNT(DISTINCT COALESCE(NULLIF(url,''), CAST(id AS TEXT))) FROM kb_entries"
        ).fetchone()[0]

    return _build_tree(rows, total_items)


def _build_tree(rows, total_items: int) -> dict:
    topics: dict = {}
    entry_seen: set = set()

    for row in rows:
        t = row["topic"]
        d = row["dimension"]
        eid = row["id"]
        topics.setdefault(t, {"dimensions": {}})
        topics[t]["dimensions"].setdefault(d, {"points": [], "sources": []})

        pt = row["point"]
        if pt and pt not in topics[t]["dimensions"][d]["points"]:
            topics[t]["dimensions"][d]["points"].append(pt)

        if eid not in entry_seen:
            entry_seen.add(eid)
            created = row["created_at"] or ""
            topics[t]["dimensions"][d]["sources"].append({
                "title": row["title"] or "",
                "url": row["url"] or "",
                "summary": row["summary"] or "",
                "date": created[:10],
                "content_form": row["content_form"] if "content_form" in row.keys() else "",
            })

    return {
        "topics": topics,
        "total_items": total_items,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def get_stats() -> dict:
    if USE_POSTGRES:
        return _pg_get_stats()
    return _sqlite_get_stats()


def _pg_get_stats() -> dict:
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(DISTINCT COALESCE(NULLIF(url,''), id::text)) FROM kb_entries"
            )
            total_items = cur.fetchone()[0]
            cur.execute("SELECT COUNT(DISTINCT topic) FROM kb_entries")
            total_topics = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(DISTINCT topic || '|' || dimension) FROM kb_entries"
            )
            total_dims = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM kb_points")
            total_points = cur.fetchone()[0]

    return {
        "total_items": total_items,
        "total_topics": total_topics,
        "total_dimensions": total_dims,
        "total_points": total_points,
    }


def _sqlite_get_stats() -> dict:
    with _sqlite_conn() as conn:
        total_items = conn.execute(
            "SELECT COUNT(DISTINCT COALESCE(NULLIF(url,''), CAST(id AS TEXT))) FROM kb_entries"
        ).fetchone()[0]
        total_topics = conn.execute(
            "SELECT COUNT(DISTINCT topic) FROM kb_entries"
        ).fetchone()[0]
        total_dims = conn.execute(
            "SELECT COUNT(DISTINCT topic || '|' || dimension) FROM kb_entries"
        ).fetchone()[0]
        total_points = conn.execute("SELECT COUNT(*) FROM kb_points").fetchone()[0]

    return {
        "total_items": total_items,
        "total_topics": total_topics,
        "total_dimensions": total_dims,
        "total_points": total_points,
    }
