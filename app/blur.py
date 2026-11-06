"""Blurs faces and person heads in place. Runs before any frame is stored or streamed."""
import cv2

_FACE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
if _FACE.empty():
    # Refuse to start rather than store frames with faces unblurred.
    raise RuntimeError("Face cascade not found. Install opencv-python-headless<5 (it ships the cascade files).")


def _blur_box(img, x0, y0, x1, y1):
    h, w = img.shape[:2]
    x0, y0 = max(0, int(x0)), max(0, int(y0))
    x1, y1 = min(w, int(x1)), min(h, int(y1))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return
    roi = img[y0:y1, x0:x1]
    k = max(21, (min(roi.shape[:2]) // 2) | 1)
    img[y0:y1, x0:x1] = cv2.GaussianBlur(roi, (k, k), 0)


def blur_faces(img, person_boxes=()):
    """Blur every detected face, plus the top third of each person box.
    The top third covers the head even when the face detector misses a side-on face."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = _FACE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(28, 28))
    for (x, y, w, h) in faces:
        pad = int(0.2 * w)
        _blur_box(img, x - pad, y - pad, x + w + pad, y + h + pad)
    for (x0, y0, x1, y1) in person_boxes:
        _blur_box(img, x0, y0, x1, y0 + int((y1 - y0) * 0.33))
    return img
