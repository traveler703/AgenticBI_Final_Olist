from __future__ import annotations

import json
import queue
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from orchestration import supervisor
from datastore import app_db
from core.config import get_settings
from datastore.olist_db import healthcheck as warehouse_healthcheck
from datastore.olist_db import refresh_log
from llm.client import chat, healthcheck as llm_healthcheck, list_models

app = FastAPI(title="Agentic BI · Olist", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _startup():
    app_db.bootstrap()


class ChatReq(BaseModel):
    message: str
    conversation_id: int | None = None
    provider: str | None = None
    model: str | None = None


class NewConvReq(BaseModel):
    provider: str | None = None
    model: str | None = None


class RenameReq(BaseModel):
    title: str


def _sse(event, data):
    return f"data: {json.dumps({'event': event, 'data': data}, ensure_ascii=False)}\n\n"


def _gen_title(question, provider, model):
    try:
        t = chat("给对话起一个不超过12字的简洁中文标题，只输出标题本身，不要标点。",
                 question, provider=provider, model=model, temperature=0.3).strip()
        return (t or question)[:24]
    except Exception:
        return question[:24]


@app.post("/api/chat")
def chat_endpoint(req: ChatReq):
    s = get_settings()
    provider = req.provider or s.llm_provider
    model = req.model

    is_new = req.conversation_id is None
    if is_new:
        cid = app_db.create_conversation(provider, model or "", title=req.message[:24])
    else:
        cid = req.conversation_id

    def stream():
        yield _sse("conversation", {"id": cid, "is_new": is_new})
        q: queue.Queue = queue.Queue()
        SENTINEL = object()

        def work():
            try:
                conv = app_db.get_conversation(cid) or {}
                history = app_db.recent_messages(cid, 6)
                app_db.add_message(cid, "user", req.message)
                result = supervisor.run(req.message, history=history, summary=conv.get("summary", ""),
                                        provider=provider, model=model, conversation_id=cid, emit=q.put)
                meta = {"charts": result["charts"], "queries": result["queries"],
                        "anomalies": result["anomalies"]}
                msg_id = app_db.add_message(cid, "assistant", result["answer"], meta=meta)
                app_db.set_summary(cid, (req.message + " → " + result["answer"])[:600])
                title = None
                if is_new:
                    title = _gen_title(req.message, provider, model)
                    app_db.rename_conversation(cid, title)
                q.put({"type": "done", "message_id": msg_id, "title": title,
                       "answer": result["answer"], "charts": result["charts"],
                       "queries": result["queries"], "anomalies": result["anomalies"]})
            except Exception as e:
                import traceback
                traceback.print_exc()
                q.put({"type": "error", "message": str(e)})
            finally:
                q.put(SENTINEL)

        threading.Thread(target=work, daemon=True).start()
        while True:
            ev = q.get()
            if ev is SENTINEL:
                break
            yield _sse(ev.get("type", "status"), ev)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/conversations")
def list_convs():
    return {"conversations": app_db.list_conversations()}


@app.post("/api/conversations")
def new_conv(req: NewConvReq):
    s = get_settings()
    cid = app_db.create_conversation(req.provider or s.llm_provider, req.model or "")
    return {"id": cid, "title": "新对话"}


@app.get("/api/conversations/{cid}/messages")
def conv_messages(cid: int):
    conv = app_db.get_conversation(cid)
    return {"conversation": conv, "messages": app_db.list_messages(cid)}


@app.patch("/api/conversations/{cid}")
def rename_conv(cid: int, req: RenameReq):
    app_db.rename_conversation(cid, req.title)
    return {"ok": True}


@app.delete("/api/conversations/{cid}")
def delete_conv(cid: int):
    app_db.delete_conversation(cid)
    return {"ok": True}


@app.get("/api/models")
def models():
    return list_models()


@app.get("/api/route_stats")
def route_stats():
    return app_db.route_stats()


@app.get("/api/refresh_log")
def refresh_log_endpoint():
    return {"rows": refresh_log()}


@app.get("/api/health")
def health():
    checks = {
        "warehouse": warehouse_healthcheck(),
        "runtime_db": app_db.healthcheck(),
        "llm": llm_healthcheck(),
    }
    healthy = all(check.get("ok") for check in checks.values())
    payload = {"status": "healthy" if healthy else "unhealthy", "checks": checks}
    return JSONResponse(payload, status_code=200 if healthy else 503)
