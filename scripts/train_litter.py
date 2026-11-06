"""Fine-tune YOLO11 on the pLitterStreet YOLO dataset and report honest test numbers.

Usage (GPU):
    python scripts/train_litter.py --data data/plitter_yolo/data.yaml --weights yolo11s.pt --epochs 60 --device 0
Writes runs/litter/train/weights/best.pt and runs/litter/eval.json.
Reports per-class precision/recall/mAP on the test split, plus detections per image on
images with no labelled litter (false alarms), which is the number that matters for enforcement.
"""
import argparse
import json
from pathlib import Path

from ultralytics import YOLO


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--weights", default="yolo11s.pt")
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--device", default="0")
    ap.add_argument("--conf", type=float, default=0.25)
    args = ap.parse_args()

    model = YOLO(args.weights)
    model.train(
        data=args.data, epochs=args.epochs, imgsz=args.imgsz, batch=args.batch,
        device=args.device, project="runs/litter", name="train", exist_ok=True,
        patience=15, cos_lr=True, seed=0,
    )
    best = YOLO("runs/litter/train/weights/best.pt")

    metrics = best.val(data=args.data, split="test", device=args.device, conf=args.conf)
    per_class = {}
    for i, name in best.names.items():
        if i < len(metrics.box.p):
            per_class[name] = {
                "precision": float(metrics.box.p[i]), "recall": float(metrics.box.r[i]),
                "mAP50": float(metrics.box.ap50[i]),
            }
    overall = {"precision": float(metrics.box.mp), "recall": float(metrics.box.mr), "mAP50": float(metrics.box.map50)}

    # False alarms: run on test images whose label file is empty.
    data_root = Path(args.data).parent
    neg_dir = data_root / "labels" / "test"
    negatives = [p.stem for p in neg_dir.glob("*.txt") if p.read_text().strip() == ""]
    img_dir = data_root / "images" / "test"
    neg_paths = [str(img_dir / f"{s}.jpg") for s in negatives if (img_dir / f"{s}.jpg").exists()]
    false_alarm_boxes = 0
    if neg_paths:
        for result in best.predict(neg_paths, conf=args.conf, device=args.device, stream=True, verbose=False):
            false_alarm_boxes += len(result.boxes)
    report = {
        "test_overall": overall, "test_per_class": per_class,
        "negative_images": len(neg_paths), "false_alarm_boxes": false_alarm_boxes,
        "false_alarms_per_negative_image": (false_alarm_boxes / len(neg_paths)) if neg_paths else None,
        "conf": args.conf, "weights": args.weights, "epochs": args.epochs, "imgsz": args.imgsz,
    }
    Path("runs/litter").mkdir(parents=True, exist_ok=True)
    Path("runs/litter/eval.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
