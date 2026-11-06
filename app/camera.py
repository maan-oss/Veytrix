"""One thread per camera. Reads, blurs, streams, keeps a pre-roll, and cuts a clip when a detection fires."""
import collections
import threading
import time
import traceback

import cv2
import numpy as np

from . import blur, config, store


def _offline_jpeg():
    img = np.full((360, 640, 3), 236, np.uint8)
    cv2.putText(img, "No signal", (236, 190), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (130, 130, 135), 2)
    return cv2.imencode(".jpg", img)[1].tobytes()


OFFLINE_JPEG = _offline_jpeg()


class CameraWorker(threading.Thread):
    def __init__(self, cam, hub):
        super().__init__(daemon=True, name=f"cam-{cam['id']}")
        self.cam = cam
        self.hub = hub
        self.lock = threading.Lock()
        self.jpeg = None
        self.online = False
        self.error = None
        self.fps = 0.0
        self.last_event_ts = 0.0
        self._recent = collections.deque(maxlen=int(config.PRE_ROLL_S * 30) + 30)
        self._pending = []
        self._boxes = []
        self._boxes_ts = 0.0
        self._persons = []
        self._last_encode = 0.0

    @property
    def cid(self):
        return self.cam["id"]

    def status(self):
        return {
            "id": self.cid,
            "name": self.cam["name"],
            "place": self.cam["place"],
            "online": self.online,
            "fps": round(self.fps, 1),
            "error": self.error,
            "enabled": self.hub.camera_enabled(self.cid),
        }

    def latest_jpeg(self):
        with self.lock:
            return self.jpeg or OFFLINE_JPEG

    def run(self):
        # Fail closed: an error drops the frame in flight (nothing unblurred is stored or streamed)
        # and restarts capture, instead of silently killing the camera thread.
        while True:
            try:
                self._run_forever()
            except Exception as exc:
                self.online, self.error = False, f"Restarting after error: {exc}"
                traceback.print_exc()
                time.sleep(2)

    def _run_forever(self):
        cap = None
        frames_done = 0
        t_fps, n_fps = time.time(), 0
        while True:
            if not self.hub.camera_enabled(self.cid):
                if cap is not None:
                    cap.release()
                    cap = None
                self.online, self.error = False, "Turned off"
                time.sleep(0.5)
                continue
            if cap is None:
                cap = cv2.VideoCapture(self.cam["source"])
                if not cap.isOpened():
                    cap.release()
                    cap = None
                    self.online, self.error = False, "Cannot open this source"
                    time.sleep(3)
                    continue
            ok, frame = cap.read()
            if not ok:
                cap.release()
                cap = None
                self.online, self.error = False, "Stream stopped, retrying"
                time.sleep(2)
                continue
            self.online, self.error = True, None

            h, w = frame.shape[:2]
            if w > config.PROCESS_WIDTH:
                frame = cv2.resize(frame, (config.PROCESS_WIDTH, int(h * config.PROCESS_WIDTH / w)),
                                   interpolation=cv2.INTER_AREA)
            now = time.time()
            frames_done += 1

            # Detection runs on the in-memory frame. Only blurred frames are stored or streamed.
            trigger = None
            if (frames_done % config.INFER_EVERY == 0 and self.hub.detector.ready
                    and self.hub.detection_enabled()):
                trigger = self._infer(frame, now)

            blur.blur_faces(frame, self._persons)
            self._recent.append((now, frame))

            for clip in list(self._pending):
                clip["frames"].append((now, frame))
                if now >= clip["until"]:
                    self._pending.remove(clip)
                    threading.Thread(target=self._write_clip, args=(clip,), daemon=True).start()

            if trigger:
                self._start_event(trigger[0], trigger[1], frame, now)

            if now - self._last_encode >= 1 / 12:
                self._last_encode = now
                view = frame.copy()
                if now - self._boxes_ts < 1.0:
                    for kind, score, (x0, y0, x1, y1) in self._boxes:
                        col = (227, 113, 0) if kind == "litter" else (0, 159, 255)
                        cv2.rectangle(view, (x0, y0), (x1, y1), col, 2)
                        cv2.putText(view, f"{kind} {score:.0%}", (x0, max(16, y0 - 6)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 2)
                ok_j, buf = cv2.imencode(".jpg", view, [cv2.IMWRITE_JPEG_QUALITY, 78])
                if ok_j:
                    with self.lock:
                        self.jpeg = buf.tobytes()

            n_fps += 1
            if now - t_fps >= 2.0:
                self.fps = n_fps / (now - t_fps)
                t_fps, n_fps = now, 0

    def _infer(self, frame, now):
        settings = self.hub.settings()
        conf = config.SENSITIVITY_CONF.get(settings["sensitivity"], 0.5)
        with self.hub.infer_lock:
            events, persons = self.hub.detector.run(frame, conf)
        self._persons = persons
        self._boxes, self._boxes_ts = events, now
        if not events or now - self.last_event_ts < settings["cooldown_s"]:
            return None
        kind, score, _ = max(events, key=lambda e: e[1])
        self.last_event_ts = now
        return kind, score

    def _start_event(self, kind, score, frame, now):
        eid = store.new_id()
        photo = f"{eid}.jpg"
        cv2.imwrite(str(config.MEDIA / photo), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        pre = [(t, f) for t, f in self._recent if now - t <= config.PRE_ROLL_S]
        self._pending.append({"eid": eid, "frames": pre, "until": now + config.POST_ROLL_S})
        store.add_event(
            id=eid, kind=kind, camera_id=self.cid, camera_name=self.cam["name"],
            place=self.cam["place"], ts=now, confidence=round(score, 3),
            status="new", photo=photo,
        )
        self.hub.notify()

    def _write_clip(self, clip):
        frames = clip["frames"]
        if len(frames) < 2:
            return
        span = max(frames[-1][0] - frames[0][0], 0.1)
        fps = min(30.0, max(1.0, (len(frames) - 1) / span))
        h, w = frames[0][1].shape[:2]
        rel = f"{clip['eid']}.mp4"
        writer = cv2.VideoWriter(str(config.MEDIA / rel), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        for _, frame in frames:
            writer.write(frame)
        writer.release()
        store.update_event(clip["eid"], clip=rel)
        self.hub.notify()
