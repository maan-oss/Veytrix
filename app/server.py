"""HTTP API and the web UI. Run with: uvicorn app.server:app --host 0.0.0.0 --port 8000"""
import time
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, notices, store
from .hub import Hub

hub = Hub()
app = FastAPI(title="Veytrix")
STATES = ("new", "reviewed", "noticed", "dismissed")
SENSITIVITY = ("low", "balanced", "high")


def present(ev):
    eid = ev["id"]
    t = time.localtime(ev["ts"])
    return {
        **ev,
        "time": time.strftime("%H:%M", t),
        "date": time.strftime("%d %b", t),
        "kind_label": "Littering" if ev["kind"] == "litter" else "Spitting",
        "photo_url": f"/api/media/{eid}/photo" if ev.get("photo") else None,
        "clip_url": f"/api/media/{eid}/clip" if ev.get("clip") else None,
        "has_notice": ev.get("notice_at") is not None,
    }


def _worker(cid):
    worker = hub.workers.get(cid)
    if worker is None:
        raise HTTPException(404, "No such camera")
    return worker


class StatusIn(BaseModel):
    status: str


class EnabledIn(BaseModel):
    enabled: bool


class SettingsIn(BaseModel):
    detection_enabled: Optional[bool] = None
    sensitivity: Optional[str] = None
    cooldown_s: Optional[int] = None


@app.get("/api/status")
def get_status():
    return hub.status()


@app.get("/api/version")
def get_version():
    return {"version": hub.version()}


@app.get("/api/cameras/{cid}/stream")
def camera_stream(cid: str):
    worker = _worker(cid)

    def frames():
        while True:
            data = worker.latest_jpeg()
            yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                   + str(len(data)).encode() + b"\r\n\r\n" + data + b"\r\n")
            time.sleep(1 / 12)

    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})


@app.get("/api/cameras/{cid}/snapshot")
def camera_snapshot(cid: str):
    return Response(_worker(cid).latest_jpeg(), media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@app.post("/api/cameras/{cid}/enabled")
def camera_enabled(cid: str, body: EnabledIn):
    _worker(cid)
    off = [c for c in hub.settings()["disabled_cameras"] if c != cid]
    if not body.enabled:
        off.append(cid)
    hub.update_settings(disabled_cameras=off)
    return hub.status()


@app.get("/api/events")
def list_events(kind: Optional[str] = None, status: Optional[str] = None,
                q: Optional[str] = None, limit: int = 200):
    query = (q or "").strip().lower() or None
    rows = store.list_events(kind=kind, status=status, q=query, limit=min(max(limit, 1), 500))
    return [present(e) for e in rows]


@app.get("/api/events/{eid}")
def get_event(eid: str):
    ev = store.get_event(eid)
    if not ev:
        raise HTTPException(404, "No such event")
    return present(ev)


@app.patch("/api/events/{eid}")
def set_status(eid: str, body: StatusIn):
    if body.status not in STATES:
        raise HTTPException(400, "Unknown status")
    if not store.get_event(eid):
        raise HTTPException(404, "No such event")
    store.update_event(eid, status=body.status)
    hub.notify()
    return present(store.get_event(eid))


@app.post("/api/events/{eid}/notice")
def write_notice(eid: str):
    ev = store.get_event(eid)
    if not ev:
        raise HTTPException(404, "No such event")
    notices.write_notice(ev)
    store.update_event(eid, status="noticed", notice_at=time.time())
    hub.notify()
    return present(store.get_event(eid))


@app.get("/api/events/{eid}/notice")
def read_notice(eid: str):
    text = notices.read_notice(eid)
    if text is None:
        raise HTTPException(404, "No notice written yet")
    return PlainTextResponse(text)


def _range_response(path, request, media_type):
    size = path.stat().st_size
    header = request.headers.get("range")
    if not header:
        return FileResponse(path, media_type=media_type)
    spec = header.replace("bytes=", "", 1).split("-", 1)
    start = int(spec[0]) if spec[0] else max(0, size - int(spec[1]))
    end = int(spec[1]) if len(spec) > 1 and spec[1] else size - 1
    end = min(end, size - 1)
    if start > end or start >= size:
        raise HTTPException(416, "Range not satisfiable")
    length = end - start + 1

    def chunks():
        with open(path, "rb") as f:
            f.seek(start)
            left = length
            while left > 0:
                data = f.read(min(1 << 16, left))
                if not data:
                    break
                left -= len(data)
                yield data

    return StreamingResponse(chunks(), status_code=206, media_type=media_type, headers={
        "Content-Range": f"bytes {start}-{end}/{size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
    })


@app.get("/api/media/{eid}/{kind}")
def media(eid: str, kind: str, request: Request):
    ev = store.get_event(eid)
    if not ev:
        raise HTTPException(404, "No such event")
    if kind == "photo" and ev.get("photo"):
        return FileResponse(config.MEDIA / ev["photo"], media_type="image/jpeg")
    if kind == "clip" and ev.get("clip"):
        return _range_response(config.MEDIA / ev["clip"], request, "video/mp4")
    raise HTTPException(404, "No such media")


@app.get("/api/settings")
def get_settings():
    return hub.settings()


@app.patch("/api/settings")
def patch_settings(body: SettingsIn):
    changes = {}
    if body.detection_enabled is not None:
        changes["detection_enabled"] = body.detection_enabled
    if body.sensitivity is not None:
        if body.sensitivity not in SENSITIVITY:
            raise HTTPException(400, "Sensitivity must be low, balanced or high")
        changes["sensitivity"] = body.sensitivity
    if body.cooldown_s is not None:
        changes["cooldown_s"] = max(5, min(600, int(body.cooldown_s)))
    return hub.update_settings(**changes)


@app.middleware("http")
async def ui_no_cache(request: Request, call_next):
    # The UI is edited often on a local install: always revalidate, so a browser never runs stale code.
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/", StaticFiles(directory=str(config.ROOT / "static"), html=True), name="ui")
