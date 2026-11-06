"""Paths and tunables. Every value can be overridden with an environment variable."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("VEYTRIX_DATA", ROOT / "data"))
MEDIA = DATA / "media"
OUTBOX = DATA / "outbox"
DB_PATH = DATA / "events.db"
SETTINGS_PATH = DATA / "settings.json"
CAMERAS_PATH = Path(os.environ.get("VEYTRIX_CAMERAS", ROOT / "cameras.json"))
MODEL_PATH = os.environ.get("VEYTRIX_MODEL", "").strip()

PROCESS_WIDTH = 960      # every frame is scaled to this width before processing
INFER_EVERY = 3          # run the detector on every Nth frame
PRE_ROLL_S = 3.0         # seconds kept before a detection
POST_ROLL_S = 3.0        # seconds recorded after a detection

DEFAULT_SETTINGS = {
    "detection_enabled": True,
    "sensitivity": "balanced",
    "cooldown_s": 20,
    "disabled_cameras": [],
}
SENSITIVITY_CONF = {"low": 0.65, "balanced": 0.5, "high": 0.35}


def ensure_dirs():
    for p in (DATA, MEDIA, OUTBOX):
        p.mkdir(parents=True, exist_ok=True)


def load_cameras():
    """Read cameras.json. A source is a webcam index (0), a stream URL (rtsp://...),
    or a video file path, which is handy for testing without hardware."""
    if not CAMERAS_PATH.exists():
        return []
    cams = []
    for c in json.loads(CAMERAS_PATH.read_text(encoding="utf-8")):
        src = c["source"]
        if isinstance(src, str) and src.isdigit():
            src = int(src)
        cams.append({
            "id": str(c["id"]),
            "name": c.get("name", str(c["id"])),
            "place": c.get("place", ""),
            "source": src,
        })
    return cams
