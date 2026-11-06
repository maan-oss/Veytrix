"""Wraps a trained YOLO model. With no weights loaded it reports why and detects nothing."""
from . import config

KIND_BY_LABEL = {
    "litter": "litter", "trash": "litter", "garbage": "litter", "rubbish": "litter",
    "spit": "spit", "spitting": "spit",
}
PERSON_LABELS = {"person"}


class Detector:
    def __init__(self):
        self.model = None
        self.error = None
        self.path = config.MODEL_PATH
        if not self.path:
            self.error = "No trained model is installed yet. Detection needs trained weights for litter and spitting."
            return
        try:
            from ultralytics import YOLO
            self.model = YOLO(self.path)
        except Exception as exc:  # missing package, bad path, bad weights
            self.error = f"Could not load the model: {exc}"

    @property
    def ready(self):
        return self.model is not None

    def run(self, frame, conf):
        """Returns (events, persons). events is [(kind, confidence, (x0, y0, x1, y1))]."""
        result = self.model.predict(frame, conf=min(conf, 0.25), verbose=False)[0]
        names = self.model.names
        events, persons = [], []
        for box in result.boxes:
            label = str(names[int(box.cls[0])]).lower()
            xyxy = tuple(int(v) for v in box.xyxy[0].tolist())
            score = float(box.conf[0])
            if label in PERSON_LABELS:
                persons.append(xyxy)
            elif label in KIND_BY_LABEL and score >= conf:
                events.append((KIND_BY_LABEL[label], score, xyxy))
        return events, persons
