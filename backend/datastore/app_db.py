"""运行时业务库 agentic_app：对话历史、消息、记忆摘要、查询审计。与 Olist 数据仓库物理分离。

会话以数据库自增主键 conversation id 唯一标识（不再用客户端字符串）。
每条消息的图表/SQL 产物存 messages.meta，供前端按消息回看历史产物；
query_route_log 是独立的聚合审计表（视图命中率/加速比），按 conversation_id 溯源。
"""
from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
import time

from sqlalchemy import create_engine, text

from core.config import get_settings

DDL = [
    """CREATE TABLE IF NOT EXISTS conversations (
        id         BIGINT AUTO_INCREMENT PRIMARY KEY,
        title      VARCHAR(255),
        provider   VARCHAR(32),
        model      VARCHAR(64),
        summary    MEDIUMTEXT,
        created_at DATETIME,
        updated_at DATETIME
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS messages (
        id              BIGINT AUTO_INCREMENT PRIMARY KEY,
        conversation_id BIGINT NOT NULL,
        role            VARCHAR(16),
        content         MEDIUMTEXT,
        meta            JSON,
        created_at      DATETIME,
        INDEX idx_msg_conv (conversation_id, id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS query_route_log (
        id              BIGINT AUTO_INCREMENT PRIMARY KEY,
        ts              DATETIME,
        conversation_id BIGINT,
        question        TEXT,
        route           VARCHAR(16),
        matched_view    VARCHAR(64),
        sql_text        TEXT,
        elapsed_ms      INT,
        INDEX idx_qrl_conv (conversation_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
]


@lru_cache
def _engine():
    return create_engine(get_settings().app_url, pool_pre_ping=True)


def bootstrap():
    s = get_settings()
    with create_engine(s.app_server_url, pool_pre_ping=True).begin() as c:
        c.execute(text(f"CREATE DATABASE IF NOT EXISTS `{s.app_db}` "
                       "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
    with _engine().begin() as c:
        for ddl in DDL:
            c.execute(text(ddl))
    print(f"[app_db] {s.app_db} ready", flush=True)


# ---------- conversations ----------
def create_conversation(provider, model, title="新对话") -> int:
    now = datetime.now()
    with _engine().begin() as c:
        r = c.execute(text(
            "INSERT INTO conversations (title,provider,model,summary,created_at,updated_at) "
            "VALUES (:ti,:p,:m,'',:n,:n)"),
            {"ti": title, "p": provider, "m": model, "n": now})
        return int(r.lastrowid)


def list_conversations():
    with _engine().connect() as c:
        rows = c.execute(text("SELECT id,title,provider,model,updated_at FROM conversations "
                              "ORDER BY updated_at DESC LIMIT 200")).mappings().all()
    return [{**r, "updated_at": str(r["updated_at"])} for r in rows]


def get_conversation(cid):
    with _engine().connect() as c:
        r = c.execute(text("SELECT id,title,provider,model,summary FROM conversations WHERE id=:i"),
                      {"i": cid}).mappings().first()
    return dict(r) if r else None


def rename_conversation(cid, title):
    with _engine().begin() as c:
        c.execute(text("UPDATE conversations SET title=:ti, updated_at=:n WHERE id=:i"),
                  {"ti": title[:255], "i": cid, "n": datetime.now()})


def delete_conversation(cid):
    with _engine().begin() as c:
        c.execute(text("DELETE FROM messages WHERE conversation_id=:i"), {"i": cid})
        c.execute(text("DELETE FROM conversations WHERE id=:i"), {"i": cid})


def touch(cid):
    with _engine().begin() as c:
        c.execute(text("UPDATE conversations SET updated_at=:n WHERE id=:i"), {"i": cid, "n": datetime.now()})


def set_summary(cid, summary):
    with _engine().begin() as c:
        c.execute(text("UPDATE conversations SET summary=:s WHERE id=:i"), {"s": summary, "i": cid})


# ---------- messages ----------
def add_message(cid, role, content, meta=None) -> int:
    with _engine().begin() as c:
        r = c.execute(text("INSERT INTO messages (conversation_id,role,content,meta,created_at) "
                           "VALUES (:i,:r,:c,:m,:n)"),
                      {"i": cid, "r": role, "c": content,
                       "m": json.dumps(meta, ensure_ascii=False) if meta else None, "n": datetime.now()})
    touch(cid)
    return int(r.lastrowid)


def list_messages(cid):
    with _engine().connect() as c:
        rows = c.execute(text("SELECT id,role,content,meta,created_at FROM messages "
                              "WHERE conversation_id=:i ORDER BY id"), {"i": cid}).mappings().all()
    return [{"id": r["id"], "role": r["role"], "content": r["content"],
             "meta": json.loads(r["meta"]) if r["meta"] else None, "created_at": str(r["created_at"])}
            for r in rows]


def recent_messages(cid, k=6):
    with _engine().connect() as c:
        rows = c.execute(text("SELECT role,content FROM messages WHERE conversation_id=:i "
                              "ORDER BY id DESC LIMIT :k"), {"i": cid, "k": k}).mappings().all()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


# ---------- query audit（聚合统计用，不喂 UI）----------
def log_query_route(cid, question, route, matched_view, sql_text, elapsed_ms):
    try:
        with _engine().begin() as c:
            c.execute(text("INSERT INTO query_route_log (ts,conversation_id,question,route,matched_view,sql_text,elapsed_ms) "
                           "VALUES (:ts,:i,:q,:r,:mv,:s,:ms)"),
                      {"ts": datetime.now(), "i": cid, "q": (question or "")[:2000], "r": route,
                       "mv": matched_view, "s": (sql_text or "")[:4000], "ms": elapsed_ms})
    except Exception as e:
        print(f"[app_db] route log failed: {e}", flush=True)


def route_stats():
    try:
        with _engine().connect() as c:
            rows = c.execute(text("SELECT route, COUNT(*) n, AVG(elapsed_ms) avg_ms "
                                  "FROM query_route_log GROUP BY route")).mappings().all()
        total = sum(r["n"] for r in rows)
        by = {r["route"]: {"count": int(r["n"]), "avg_ms": float(r["avg_ms"] or 0)} for r in rows}
        mv = by.get("MV", {}).get("count", 0)
        return {"total": int(total), "mv_hit_rate": (mv / total) if total else 0.0, "by_route": by}
    except Exception as e:
        return {"total": 0, "mv_hit_rate": 0.0, "by_route": {}, "error": str(e)}


def healthcheck() -> dict:
    """Check that the runtime database is reachable and its core tables exist."""
    started = time.perf_counter()
    try:
        with _engine().connect() as c:
            c.execute(text("SELECT 1")).scalar()
            for table in ("conversations", "messages", "query_route_log"):
                c.execute(text(f"SELECT 1 FROM `{table}` LIMIT 1")).first()
        return {"ok": True, "latency_ms": int((time.perf_counter() - started) * 1000)}
    except Exception as exc:
        return {
            "ok": False,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error": str(exc)[:300],
        }
