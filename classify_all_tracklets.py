from __future__ import annotations

import argparse
import csv
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import torch
import torch.nn as nn
from PIL import Image, ImageOps
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from torchvision.models import mobilenet_v3_small

try:
    from torchvision.models import MobileNet_V3_Small_Weights
except ImportError:
    MobileNet_V3_Small_Weights = None


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
IMAGE_NET_MEAN = [0.485, 0.456, 0.406]
IMAGE_NET_STD = [0.229, 0.224, 0.225]


@dataclass(frozen=True)
class ImageItem:
    sequence: str
    track: str
    image_name: str
    source_path: Path


class SquarePad:
    """Padding ảnh thành hình vuông mà không làm méo cầu thủ."""

    def __init__(self, fill: int = 0) -> None:
        self.fill = fill

    def __call__(self, image: Image.Image) -> Image.Image:
        width, height = image.size
        max_side = max(width, height)

        pad_left = (max_side - width) // 2
        pad_right = max_side - width - pad_left
        pad_top = (max_side - height) // 2
        pad_bottom = max_side - height - pad_top

        return ImageOps.expand(
            image,
            border=(pad_left, pad_top, pad_right, pad_bottom),
            fill=self.fill,
        )


class TrackletDataset(Dataset):
    def __init__(
        self,
        items: List[ImageItem],
        transform,
    ) -> None:
        self.items = items
        self.transform = transform

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int):
        item = self.items[index]

        try:
            with Image.open(item.source_path) as image:
                image = image.convert("RGB")
                tensor = self.transform(image)
        except Exception as error:
            raise RuntimeError(
                f"Không đọc được ảnh: {item.source_path}"
            ) from error

        return tensor, index


def find_images(input_root: Path) -> List[ImageItem]:
    """
    Mong đợi:
        input_root/
        ├── SNMOT-060/
        │   ├── track_0001/
        │   │   ├── frame_000001.jpg
        │   │   └── ...
        │   └── track_0002/
        └── SNMOT-061/
    """

    items: List[ImageItem] = []

    for sequence_dir in sorted(input_root.iterdir()):
        if not sequence_dir.is_dir():
            continue

        if sequence_dir.name.lower() == "check_results":
            continue

        for track_dir in sorted(sequence_dir.iterdir()):
            if not track_dir.is_dir():
                continue

            if not track_dir.name.lower().startswith("track_"):
                continue

            for image_path in sorted(track_dir.iterdir()):
                if (
                    image_path.is_file()
                    and image_path.suffix.lower() in IMAGE_EXTENSIONS
                ):
                    items.append(
                        ImageItem(
                            sequence=sequence_dir.name,
                            track=track_dir.name,
                            image_name=image_path.name,
                            source_path=image_path.resolve(),
                        )
                    )

    return items


def build_transform(image_size: int):
    return transforms.Compose(
        [
            SquarePad(fill=0),
            transforms.Resize((image_size, image_size)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=IMAGE_NET_MEAN,
                std=IMAGE_NET_STD,
            ),
        ]
    )


def build_model(num_classes: int) -> nn.Module:
    if MobileNet_V3_Small_Weights is not None:
        model = mobilenet_v3_small(weights=None)
    else:
        model = mobilenet_v3_small(pretrained=False)

    input_features = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(
        input_features,
        num_classes,
    )

    return model


def load_checkpoint(
    checkpoint_path: Path,
    device: torch.device,
) -> Tuple[nn.Module, Dict[str, int], int]:
    checkpoint = torch.load(
        str(checkpoint_path),
        map_location=device,
    )

    if not isinstance(checkpoint, dict):
        raise ValueError(
            "Checkpoint không đúng định dạng dictionary."
        )

    required_keys = {
        "model_state_dict",
        "class_to_idx",
        "image_size",
    }
    missing_keys = required_keys - set(checkpoint.keys())

    if missing_keys:
        raise ValueError(
            "Checkpoint thiếu key: "
            + ", ".join(sorted(missing_keys))
        )

    class_to_idx = checkpoint["class_to_idx"]

    if not isinstance(class_to_idx, dict):
        raise ValueError("class_to_idx trong checkpoint không hợp lệ.")

    if "legible" not in class_to_idx or "not_legible" not in class_to_idx:
        raise ValueError(
            "Checkpoint phải có class legible và not_legible."
        )

    image_size = int(checkpoint["image_size"])

    model = build_model(num_classes=len(class_to_idx))
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()

    return model, class_to_idx, image_size


def transfer_file(
    source: Path,
    destination: Path,
    mode: str,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)

    if mode == "copy":
        shutil.copy2(source, destination)
        return

    if mode == "hardlink":
        try:
            destination.hardlink_to(source)
        except OSError:
            shutil.copy2(source, destination)
        return

    if mode == "none":
        return

    raise ValueError(f"Mode không hợp lệ: {mode}")


def prepare_output(
    output_root: Path,
    overwrite: bool,
) -> None:
    if output_root.exists() and any(output_root.iterdir()):
        if not overwrite:
            raise FileExistsError(
                f"Output đã có dữ liệu: {output_root}\n"
                "Thêm --overwrite để tạo lại."
            )

        shutil.rmtree(output_root)

    output_root.mkdir(parents=True, exist_ok=True)


def classify_probability(
    p_legible: float,
    legible_threshold: float,
    not_legible_threshold: float,
) -> str:
    if p_legible >= legible_threshold:
        return "legible"

    if p_legible <= not_legible_threshold:
        return "not_legible"

    return "uncertain"


def write_predictions(
    output_path: Path,
    rows: List[Dict[str, object]],
) -> None:
    fieldnames = [
        "sequence",
        "track",
        "image_name",
        "prediction",
        "p_legible",
        "p_not_legible",
        "source_path",
        "output_path",
    ]

    with output_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Dùng MobileNetV3 legibility classifier để lọc toàn bộ "
            "tracklet thành legible, not_legible và uncertain."
        )
    )

    parser.add_argument(
        "--input-root",
        type=Path,
        required=True,
        help="Thư mục soccernet_tracklets_filtered.",
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        required=True,
        help="Đường dẫn best_model.pth.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="Thư mục output.",
    )
    parser.add_argument(
        "--legible-threshold",
        type=float,
        default=0.90,
        help=(
            "P(legible) >= ngưỡng này sẽ được xếp legible. "
            "Mặc định 0.90."
        ),
    )
    parser.add_argument(
        "--not-legible-threshold",
        type=float,
        default=0.20,
        help=(
            "P(legible) <= ngưỡng này sẽ được xếp not_legible. "
            "Mặc định 0.20."
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=0,
        help="Windows nên bắt đầu bằng 0.",
    )
    parser.add_argument(
        "--mode",
        choices=("copy", "hardlink", "none"),
        default="copy",
        help=(
            "copy: sao chép ảnh; hardlink: tiết kiệm dung lượng nếu cùng ổ; "
            "none: chỉ xuất predictions.csv."
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Xóa output cũ trước khi chạy lại.",
    )

    args = parser.parse_args()

    input_root = args.input_root.resolve()
    model_path = args.model_path.resolve()
    output_root = args.output_root.resolve()

    if not input_root.is_dir():
        parser.error(f"Không tồn tại input-root: {input_root}")

    if not model_path.is_file():
        parser.error(f"Không tồn tại model-path: {model_path}")

    if input_root == output_root:
        parser.error("--input-root và --output-root phải khác nhau.")

    if not 0.0 <= args.not_legible_threshold <= 1.0:
        parser.error("--not-legible-threshold phải nằm trong [0, 1].")

    if not 0.0 <= args.legible_threshold <= 1.0:
        parser.error("--legible-threshold phải nằm trong [0, 1].")

    if args.not_legible_threshold >= args.legible_threshold:
        parser.error(
            "--not-legible-threshold phải nhỏ hơn "
            "--legible-threshold."
        )

    if args.batch_size < 1:
        parser.error("--batch-size phải >= 1.")

    try:
        prepare_output(
            output_root=output_root,
            overwrite=args.overwrite,
        )
    except FileExistsError as error:
        parser.error(str(error))

    device = torch.device(
        "cuda" if torch.cuda.is_available() else "cpu"
    )

    print("Device:", device)

    if device.type == "cuda":
        print("GPU:", torch.cuda.get_device_name(0))

    model, class_to_idx, image_size = load_checkpoint(
        checkpoint_path=model_path,
        device=device,
    )

    print("Class mapping:", class_to_idx)
    print("Image size:", image_size)

    legible_index = int(class_to_idx["legible"])
    not_legible_index = int(class_to_idx["not_legible"])

    items = find_images(input_root)

    if not items:
        raise FileNotFoundError(
            "Không tìm thấy ảnh theo cấu trúc sequence/track."
        )

    print("Images found:", len(items))

    dataset = TrackletDataset(
        items=items,
        transform=build_transform(image_size),
    )

    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=(device.type == "cuda"),
    )

    counts = {
        "legible": 0,
        "not_legible": 0,
        "uncertain": 0,
    }

    prediction_rows: List[Dict[str, object]] = []
    processed = 0

    with torch.inference_mode():
        for images, item_indexes in loader:
            images = images.to(
                device,
                non_blocking=True,
            )

            logits = model(images)
            probabilities = torch.softmax(
                logits,
                dim=1,
            ).cpu()

            for batch_position, item_index in enumerate(
                item_indexes.tolist()
            ):
                item = items[item_index]

                p_legible = float(
                    probabilities[
                        batch_position,
                        legible_index,
                    ].item()
                )
                p_not_legible = float(
                    probabilities[
                        batch_position,
                        not_legible_index,
                    ].item()
                )

                prediction = classify_probability(
                    p_legible=p_legible,
                    legible_threshold=args.legible_threshold,
                    not_legible_threshold=args.not_legible_threshold,
                )

                counts[prediction] += 1

                if args.mode == "none":
                    destination_text = ""
                else:
                    destination = (
                        output_root
                        / prediction
                        / item.sequence
                        / item.track
                        / item.image_name
                    )

                    transfer_file(
                        source=item.source_path,
                        destination=destination,
                        mode=args.mode,
                    )
                    destination_text = str(destination.resolve())

                prediction_rows.append(
                    {
                        "sequence": item.sequence,
                        "track": item.track,
                        "image_name": item.image_name,
                        "prediction": prediction,
                        "p_legible": round(p_legible, 8),
                        "p_not_legible": round(
                            p_not_legible,
                            8,
                        ),
                        "source_path": str(item.source_path),
                        "output_path": destination_text,
                    }
                )

                processed += 1

            if processed % 1000 < args.batch_size:
                print(
                    f"[{processed}/{len(items)}] "
                    f"legible={counts['legible']} | "
                    f"not_legible={counts['not_legible']} | "
                    f"uncertain={counts['uncertain']}"
                )

    predictions_csv = output_root / "predictions.csv"

    write_predictions(
        output_path=predictions_csv,
        rows=prediction_rows,
    )

    summary = {
        "input_root": str(input_root),
        "model_path": str(model_path),
        "output_root": str(output_root),
        "device": str(device),
        "image_size": image_size,
        "class_to_idx": class_to_idx,
        "thresholds": {
            "legible_threshold": args.legible_threshold,
            "not_legible_threshold": args.not_legible_threshold,
        },
        "counts": {
            **counts,
            "total": len(items),
        },
        "ratios": {
            "legible": counts["legible"] / len(items),
            "not_legible": counts["not_legible"] / len(items),
            "uncertain": counts["uncertain"] / len(items),
        },
    }

    summary_json = output_root / "summary.json"
    summary_json.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    summary_txt = output_root / "summary.txt"
    summary_txt.write_text(
        "\n".join(
            [
                "========== LEGIBILITY INFERENCE ==========",
                f"Total:         {len(items)}",
                f"Legible:      {counts['legible']}",
                f"Not legible:  {counts['not_legible']}",
                f"Uncertain:    {counts['uncertain']}",
                "",
                f"Legible threshold:     {args.legible_threshold}",
                f"Not-legible threshold: {args.not_legible_threshold}",
                f"Device:                {device}",
                f"Model:                 {model_path}",
            ]
        ),
        encoding="utf-8",
    )

    print("\n========== HOÀN TẤT ==========")
    print(f"Total:        {len(items)}")
    print(f"Legible:      {counts['legible']}")
    print(f"Not legible: {counts['not_legible']}")
    print(f"Uncertain:    {counts['uncertain']}")
    print(f"Predictions:  {predictions_csv}")
    print(f"Summary:      {summary_json}")
    print(f"Output:       {output_root}")


if __name__ == "__main__":
    main()