"""Owns the cameras, the detector and the settings. The HTTP layer talks only to this."""
import copy
import json
import threading

from . import config, store
from .camera import CameraWorker
from .detector import Detector


class Hub:
    def __init__(self):
        config.ensure_dirs()
        self.detector = Detector()
        self.infer_lock = threading.Lock()
        self._lock = threading.Lock()
        self._settings = self._load()
        self._version = 0
        self.workers = {cam["id"]: CameraWorker(cam, self) for cam in config.load_cameras()}
        for worker in self.workers.values():
            worker.start()

    def _load(self):
        settings = copy.deepcopy(config.DEFAULT_SETTINGS)
        if config.SETTINGS_PATH.exists():
            try:
                settings.update(json.loads(config.SETTINGS_PATH.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                pass
        return settings

    def settings(self):
        with self._lock:
            return copy.deepcopy(self._settings)

    def update_settings(self, **changes):
        with self._lock:
            self._settings.update(changes)
            config.SETTINGS_PATH.write_text(json.dumps(self._settings, indent=2), encoding="utf-8")
        self.notify()
        return self.settings()

    def detection_enabled(self):
        return self.settings()["detection_enabled"]

    def camera_enabled(self, cid):
        return cid not in self.settings()["disabled_cameras"]

    def notify(self):
        with self._lock:
            self._version += 1

    def version(self):
        with self._lock:
            return self._version

    def status(self):
        return {
            "detector": {"ready": self.detector.ready, "error": self.detector.error,
                         "path": self.detector.path},
            "detection_enabled": self.detection_enabled(),
            "cameras": [w.status() for w in self.workers.values()],
            "counts_24h": store.counts(),
            "paths": {"data": str(config.DATA), "media": str(config.MEDIA),
                      "outbox": str(config.OUTBOX)},
        }
