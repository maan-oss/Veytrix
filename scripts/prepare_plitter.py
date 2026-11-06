"""Convert pLitterStreet (COCO JSON) to a YOLO dataset for Veytrix.

Source: Mandhati et al., pLitterStreet, Zenodo 8288500, CC BY 4.0.
Usage:
    python scripts/prepare_plitter.py --zip-images images.zip --zip-annotations annotations.zip --out data/plitter_yolo
Uses the 4-class split (Plastic, Pile, Face mask, Trash bin).
Writes data.yaml, images/<split>/, labels/<split>/. Images with no annotations are kept as negatives.
"""
import argparse
import json
import zipfile
from pathlib import Path

import cv2
import numpy as np

_FACE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def blur_faces(img):
    """Blur every detected face (20% padding) before the image is written. Required by Veytrix privacy rules."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    for (x, y, w, h) in _FACE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24)):
        pad_w, pad_h = int(w * 0.2), int(h * 0.2)
        x1, y1 = max(0, x - pad_w), max(0, y - pad_h)
        x2, y2 = min(img.shape[1], x + w + pad_w), min(img.shape[0], y + h + pad_h)
        roi = img[y1:y2, x1:x2]
        k = max(3, (min(roi.shape[:2]) // 3) | 1)
        img[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (k, k), 0)
    return img

SPLITS = {"train": "annotations_train.json", "val": "annotations_val.json", "test": "annotations_test.json"}


def convert(coco: dict, out_labels: Path, class_map: dict):
    by_image = {}
    for ann in coco["annotations"]:
        by_image.setdefault(ann["image_id"], []).append(ann)
    lines_written = 0
    for img in coco["images"]:
        w, h = float(img["width"]), float(img["height"])
        rows = []
        for ann in by_image.get(img["id"], []):
            cls = class_map.get(ann["category_id"])
            if cls is None:
                continue
            x, y, bw, bh = ann["bbox"]
            # clip to image bounds, then normalise to YOLO centre format
            x1, y1 = max(0.0, x), max(0.0, y)
            x2, y2 = min(w, x + bw), min(h, y + bh)
            if x2 <= x1 or y2 <= y1:
                continue
            rows.append(f"{cls} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}")
        stem = Path(img["file_name"]).stem
        (out_labels / f"{stem}.txt").write_text("\n".join(rows) + ("\n" if rows else ""))
        lines_written += len(rows)
    return lines_written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip-images", required=True)
    ap.add_argument("--zip-annotations", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    ann_zip = zipfile.ZipFile(args.zip_annotations)
    img_zip = zipfile.ZipFile(args.zip_images)
    names = ["Plastic", "Pile", "Face mask", "Trash bin"]

    for split, fname in SPLITS.items():
        coco = json.load(ann_zip.open(f"annotations/4_class_splits/{fname}"))
        cats = {c["name"]: c["id"] for c in coco["categories"]}
        class_map = {cats[n]: i for i, n in enumerate(names) if n in cats}
        img_dir = out / "images" / split
        lbl_dir = out / "labels" / split
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)
        boxes = convert(coco, lbl_dir, class_map)
        wanted = {Path(i["file_name"]).name for i in coco["images"]}
        extracted = 0
        for member in img_zip.namelist():
            base = Path(member).name
            if base in wanted and not member.endswith("/"):
                raw = np.frombuffer(img_zip.read(member), dtype=np.uint8)
                img = cv2.imdecode(raw, cv2.IMREAD_COLOR)
                if img is None:
                    continue
                img = blur_faces(img)
                cv2.imwrite(str(img_dir / base), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
                extracted += 1
        print(f"{split}: images {extracted}/{len(coco['images'])}, boxes {boxes}")

    (out / "data.yaml").write_text(
        f"path: {out.resolve()}\n"
        "train: images/train\nval: images/val\ntest: images/test\n"
        f"names:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(names))
    )
    print("wrote", out / "data.yaml")


if __name__ == "__main__":
    main()
