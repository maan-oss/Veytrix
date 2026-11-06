# Veytrix

A local app that watches cameras for littering and spitting, blurs faces before anything is stored or shown, and keeps each event with a real photo or clip. Notices are written to an outbox folder. Nothing is matched to a name, and faces are never compared across cameras.

## Run it

```bash
pip install -r requirements.txt
cp cameras.example.json cameras.json        # edit: your webcams, RTSP URLs or video files
export VEYTRIX_MODEL=/path/to/weights.pt  # trained YOLO weights (see below)
pip install ultralytics                      # only needed with a model
uvicorn app.server:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` on the PC. On a phone on the same network, open `http://<PC-IP>:8000`. On iPhone or Android, use "Add to Home Screen".

## What is real and what is not

- Real: camera capture, face and head blurring, event storage (SQLite), real JPEG photos and MP4 clips, notices written to `data/outbox/<event>/` with the evidence copied in, settings that persist, and the UI on PC and phone.
- Not included: a trained litter and spitting model. Without `VEYTRIX_MODEL`, cameras stream and nothing is detected. The app says so on screen. Your weights must have labels named `litter` (or `trash`, `garbage`) and `spit` (or `spitting`). A `person` label, if present, is used to blur heads.
- Face blurring uses OpenCV's Haar face detector, which misses side-on and angled faces. The head-blur on person boxes covers most of that, but for production replace `app/blur.py` with a stronger face detector.
- Notices are files. Nothing is sent to any government system. Connecting one is a separate decision with its own legal review.

## Layout

- `app/camera.py` reads each camera, blurs frames, and cuts a clip (3 s before, 3 s after) on detection.
- `app/hub.py` holds cameras, detector and settings. `app/server.py` is the HTTP API.
- `static/` is the UI: a toolbar with the sidebar toggle at top-left on PC; a bottom tab bar on phones; sheets that morph on PC and slide up and drag down on phones.

## Before you deploy in public space

Check the privacy and surveillance rules that apply where the cameras are, and put up signage. Someone should decide who may see the outbox and how long evidence is kept. The app does not decide those for you.
