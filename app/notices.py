"""Writes a notice and its evidence into the outbox folder. Nothing is sent anywhere by this module."""
import shutil
import time

from . import config


def write_notice(ev):
    folder = config.OUTBOX / ev["id"]
    folder.mkdir(parents=True, exist_ok=True)
    evidence = [name for name in (ev.get("photo"), ev.get("clip"))
                if name and (config.MEDIA / name).exists()]
    for name in evidence:
        shutil.copy2(config.MEDIA / name, folder / name)
    when = time.strftime("%d %b %Y, %H:%M", time.localtime(ev["ts"]))
    label = "littering" if ev["kind"] == "litter" else "spitting"
    text = "\n".join([
        f"Veytrix notice {ev['id']}",
        "",
        f"Date and time: {when}",
        f"Location: {ev['place']}",
        f"Camera: {ev['camera_name']}",
        f"Event: {label}",
        f"Detection confidence: {round((ev['confidence'] or 0) * 100)}%",
        f"Evidence: {', '.join(evidence) or 'none yet'} (faces blurred at capture)",
        "",
        "This notice records an event at a location. It does not identify any individual.",
        "Requesting a patrol or cleaning response at this location.",
        "",
    ])
    (folder / "notice.txt").write_text(text, encoding="utf-8")
    return text


def read_notice(eid):
    path = config.OUTBOX / eid / "notice.txt"
    return path.read_text(encoding="utf-8") if path.exists() else None
