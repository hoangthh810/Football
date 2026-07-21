from __future__ import annotations

import argparse
import csv
import math
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
FRAME_PATTERN = re.compile(r"frame_(\d+)", flags=re.IGNORECASE)


@dataclass
class ImageCandidate:
    source_path: Path
    sequence: str
    track_name: str
    frame_id: int
    width: int
    height: int
    area: int
    sharpness: float
    size_score: float
    sharpness_score: float
    quality_score: float
    dhash: int


def parse_frame_id(path: Path) -> int:
    match = FRAME_PATTERN.search(path.stem)
    if match:
        return int(match.group(1))

    numbers = re.findall(r"\d+", path.stem)
    if numbers:
        return int(numbers[-1])

    return -1


def variance_of_laplacian(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def difference_hash(image: np.ndarray, hash_size: int = 8) -> int:
    """Tạo dHash 64-bit để phát hiện các ảnh gần trùng nhau."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(
        gray,
        (hash_size + 1, hash_size),
        interpolation=cv2.INTER_AREA,
    )
    differences = resized[:, 1:] > resized[:, :-1]

    value = 0
    for bit in differences.flatten():
        value = (value << 1) | int(bit)

    return value


def hamming_distance(hash_a: int, hash_b: int) -> int:
       return bin(hash_a ^ hash_b).count("1")


def calculate_scores(
    width: int,
    height: int,
    sharpness: float,
    target_height: int,
    target_area: int,
    sharpness_reference: float,
    size_weight: float,
    sharpness_weight: float,
) -> tuple[float, float, float]:
    """Tính điểm kích thước, độ nét và điểm chất lượng tổng hợp."""
    height_score = min(height / max(target_height, 1), 1.0)
    area_score = min((width * height) / max(target_area, 1), 1.0)
    size_score = 0.6 * height_score + 0.4 * area_score

    sharpness_score = min(
        math.log1p(max(sharpness, 0.0))
        / math.log1p(max(sharpness_reference, 1.0)),
        1.0,
    )

    total_weight = size_weight + sharpness_weight
    if total_weight <= 0:
        total_weight = 1.0

    quality_score = (
        size_weight * size_score
        + sharpness_weight * sharpness_score
    ) / total_weight

    return size_score, sharpness_score, quality_score


def find_track_directories(input_root: Path) -> list[Path]:
    """
    Mong đợi cấu trúc:
        input_root/
        ├── SNMOT-060/
        │   ├── track_0001/
        │   └── track_0002/
        └── SNMOT-061/
    """
    track_dirs: list[Path] = []

    for sequence_dir in sorted(input_root.iterdir()):
        if not sequence_dir.is_dir():
            continue

        for track_dir in sorted(sequence_dir.iterdir()):
            if track_dir.is_dir() and track_dir.name.lower().startswith("track_"):
                track_dirs.append(track_dir)

    return track_dirs


def list_images(track_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in track_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def build_candidates(
    track_dir: Path,
    args: argparse.Namespace,
) -> tuple[list[ImageCandidate], dict[str, int]]:
    sequence = track_dir.parent.name
    track_name = track_dir.name

    candidates: list[ImageCandidate] = []
    stats = {
        "total": 0,
        "unreadable": 0,
        "too_small": 0,
        "too_blurry": 0,
        "eligible": 0,
    }

    for image_path in list_images(track_dir):
        stats["total"] += 1
        image = cv2.imread(str(image_path))

        if image is None:
            stats["unreadable"] += 1
            continue

        height, width = image.shape[:2]
        area = width * height

        if (
            width < args.min_width
            or height < args.min_height
            or area < args.min_area
        ):
            stats["too_small"] += 1
            continue

        sharpness = variance_of_laplacian(image)

        if sharpness < args.min_sharpness:
            stats["too_blurry"] += 1
            continue

        size_score, sharpness_score, quality_score = calculate_scores(
            width=width,
            height=height,
            sharpness=sharpness,
            target_height=args.target_height,
            target_area=args.target_area,
            sharpness_reference=args.sharpness_reference,
            size_weight=args.size_weight,
            sharpness_weight=args.sharpness_weight,
        )

        candidates.append(
            ImageCandidate(
                source_path=image_path,
                sequence=sequence,
                track_name=track_name,
                frame_id=parse_frame_id(image_path),
                width=width,
                height=height,
                area=area,
                sharpness=sharpness,
                size_score=size_score,
                sharpness_score=sharpness_score,
                quality_score=quality_score,
                dhash=difference_hash(image),
            )
        )
        stats["eligible"] += 1

    return candidates, stats


def is_temporally_far_enough(
    candidate: ImageCandidate,
    selected: list[ImageCandidate],
    min_frame_gap: int,
) -> bool:
    if min_frame_gap <= 0 or candidate.frame_id < 0:
        return True

    for selected_item in selected:
        if selected_item.frame_id < 0:
            continue
        if abs(candidate.frame_id - selected_item.frame_id) < min_frame_gap:
            return False

    return True


def is_visually_different(
    candidate: ImageCandidate,
    selected: list[ImageCandidate],
    min_hash_distance: int,
) -> bool:
    if min_hash_distance <= 0:
        return True

    return all(
        hamming_distance(candidate.dhash, selected_item.dhash)
        >= min_hash_distance
        for selected_item in selected
    )


def select_best_images(
    candidates: list[ImageCandidate],
    max_per_track: int,
    min_frame_gap: int,
    min_hash_distance: int,
) -> tuple[list[ImageCandidate], int, int]:
    ranked = sorted(
        candidates,
        key=lambda item: (
            item.quality_score,
            item.sharpness,
            item.area,
        ),
        reverse=True,
    )

    selected: list[ImageCandidate] = []
    rejected_temporal = 0
    rejected_duplicate = 0

    for candidate in ranked:
        if len(selected) >= max_per_track:
            break

        if not is_temporally_far_enough(
            candidate,
            selected,
            min_frame_gap,
        ):
            rejected_temporal += 1
            continue

        if not is_visually_different(
            candidate,
            selected,
            min_hash_distance,
        ):
            rejected_duplicate += 1
            continue

        selected.append(candidate)

    return selected, rejected_temporal, rejected_duplicate


def copy_selected(
    selected: list[ImageCandidate],
    input_root: Path,
    output_root: Path,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    for rank, item in enumerate(selected, start=1):
        relative_path = item.source_path.relative_to(input_root)
        destination_path = output_root / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(item.source_path, destination_path)

        rows.append(
            {
                "sequence": item.sequence,
                "track": item.track_name,
                "frame_id": item.frame_id,
                "rank_in_track": rank,
                "width": item.width,
                "height": item.height,
                "area": item.area,
                "sharpness": round(item.sharpness, 4),
                "size_score": round(item.size_score, 6),
                "sharpness_score": round(item.sharpness_score, 6),
                "quality_score": round(item.quality_score, 6),
                "source_path": str(item.source_path.resolve()),
                "selected_path": str(destination_path.resolve()),
            }
        )

    return rows


def load_source_metadata(metadata_path: Path) -> list[dict[str, str]]:
    if not metadata_path.is_file():
        return []

    with metadata_path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_filtered_metadata(
    source_metadata: list[dict[str, str]],
    selected_rows: list[dict[str, object]],
    output_path: Path,
) -> None:
    """Giữ lại metadata của những crop được chọn."""
    if not source_metadata:
        return

    selected_by_source = {
        str(Path(str(row["source_path"])).resolve()): row
        for row in selected_rows
    }

    output_rows: list[dict[str, object]] = []

    for source_row in source_metadata:
        crop_path = source_row.get("crop_path", "")
        if not crop_path:
            continue

        resolved_crop_path = str(Path(crop_path).resolve())
        selected_info = selected_by_source.get(resolved_crop_path)

        if selected_info is None:
            continue

        merged: dict[str, object] = dict(source_row)
        merged.update(
            {
                "selected_path": selected_info["selected_path"],
                "rank_in_track": selected_info["rank_in_track"],
                "sharpness": selected_info["sharpness"],
                "size_score": selected_info["size_score"],
                "sharpness_score": selected_info["sharpness_score"],
                "quality_score": selected_info["quality_score"],
            }
        )
        output_rows.append(merged)

    if not output_rows:
        return

    fieldnames = list(output_rows[0].keys())

    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
    fieldnames: list[str],
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Lọc ảnh tracklet SoccerNet theo kích thước, độ nét, khoảng cách "
            "frame và độ tương đồng hình ảnh."
        )
    )

    parser.add_argument(
        "--input-root",
        type=Path,
        required=True,
        help="Thư mục tracklets đã tạo.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="Thư mục lưu ảnh đã lọc.",
    )
    parser.add_argument(
        "--max-per-track",
        type=int,
        default=20,
        help="Số ảnh tối đa giữ lại cho mỗi track. Mặc định 20.",
    )
    parser.add_argument(
        "--min-width",
        type=int,
        default=30,
        help="Bỏ ảnh có chiều rộng nhỏ hơn giá trị này.",
    )
    parser.add_argument(
        "--min-height",
        type=int,
        default=100,
        help="Bỏ ảnh có chiều cao nhỏ hơn giá trị này.",
    )
    parser.add_argument(
        "--min-area",
        type=int,
        default=4000,
        help="Bỏ ảnh có diện tích nhỏ hơn giá trị này.",
    )
    parser.add_argument(
        "--min-sharpness",
        type=float,
        default=35.0,
        help="Ngưỡng variance of Laplacian. Mặc định 35.",
    )
    parser.add_argument(
        "--min-frame-gap",
        type=int,
        default=5,
        help="Khoảng cách frame tối thiểu giữa hai ảnh được chọn.",
    )
    parser.add_argument(
        "--min-hash-distance",
        type=int,
        default=6,
        help=(
            "Hamming distance dHash tối thiểu. Cao hơn sẽ lọc ảnh gần trùng "
            "mạnh hơn. Mặc định 6."
        ),
    )
    parser.add_argument(
        "--target-height",
        type=int,
        default=300,
        help="Chiều cao dùng để chuẩn hóa điểm kích thước.",
    )
    parser.add_argument(
        "--target-area",
        type=int,
        default=30000,
        help="Diện tích dùng để chuẩn hóa điểm kích thước.",
    )
    parser.add_argument(
        "--sharpness-reference",
        type=float,
        default=250.0,
        help="Độ nét được xem là đạt điểm tối đa.",
    )
    parser.add_argument(
        "--size-weight",
        type=float,
        default=0.45,
        help="Trọng số điểm kích thước.",
    )
    parser.add_argument(
        "--sharpness-weight",
        type=float,
        default=0.55,
        help="Trọng số điểm độ nét.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.max_per_track < 1:
        parser.error("--max-per-track phải >= 1")
    if args.min_frame_gap < 0:
        parser.error("--min-frame-gap phải >= 0")
    if not 0 <= args.min_hash_distance <= 64:
        parser.error("--min-hash-distance phải nằm trong 0..64")

    input_root = args.input_root.resolve()
    output_root = args.output_root.resolve()

    if not input_root.is_dir():
        parser.error(f"Không tồn tại input root: {input_root}")

    if input_root == output_root:
        parser.error("--output-root phải khác --input-root")

    output_root.mkdir(parents=True, exist_ok=True)

    track_dirs = find_track_directories(input_root)

    if not track_dirs:
        raise FileNotFoundError(
            "Không tìm thấy thư mục track_* trong các thư mục sequence."
        )

    selected_rows: list[dict[str, object]] = []
    report_rows: list[dict[str, object]] = []

    total_input = 0
    total_selected = 0

    for index, track_dir in enumerate(track_dirs, start=1):
        candidates, stats = build_candidates(track_dir, args)

        selected, rejected_temporal, rejected_duplicate = select_best_images(
            candidates=candidates,
            max_per_track=args.max_per_track,
            min_frame_gap=args.min_frame_gap,
            min_hash_distance=args.min_hash_distance,
        )

        rows = copy_selected(
            selected=selected,
            input_root=input_root,
            output_root=output_root,
        )
        selected_rows.extend(rows)

        total_input += stats["total"]
        total_selected += len(selected)

        report_rows.append(
            {
                "sequence": track_dir.parent.name,
                "track": track_dir.name,
                "total_images": stats["total"],
                "unreadable": stats["unreadable"],
                "too_small": stats["too_small"],
                "too_blurry": stats["too_blurry"],
                "eligible_before_dedup": stats["eligible"],
                "rejected_by_frame_gap": rejected_temporal,
                "rejected_as_duplicate": rejected_duplicate,
                "selected": len(selected),
            }
        )

        if index % 100 == 0 or index == len(track_dirs):
            print(
                f"[{index}/{len(track_dirs)}] "
                f"Đã chọn {total_selected}/{total_input} ảnh."
            )

    selected_fields = [
        "sequence",
        "track",
        "frame_id",
        "rank_in_track",
        "width",
        "height",
        "area",
        "sharpness",
        "size_score",
        "sharpness_score",
        "quality_score",
        "source_path",
        "selected_path",
    ]
    write_csv(
        output_root / "selected_images.csv",
        selected_rows,
        selected_fields,
    )

    report_fields = [
        "sequence",
        "track",
        "total_images",
        "unreadable",
        "too_small",
        "too_blurry",
        "eligible_before_dedup",
        "rejected_by_frame_gap",
        "rejected_as_duplicate",
        "selected",
    ]
    write_csv(
        output_root / "filter_report.csv",
        report_rows,
        report_fields,
    )

    source_metadata = load_source_metadata(input_root / "metadata.csv")
    write_filtered_metadata(
        source_metadata=source_metadata,
        selected_rows=selected_rows,
        output_path=output_root / "filtered_metadata.csv",
    )

    print("\n========== HOÀN TẤT ==========")
    print(f"Tracks:          {len(track_dirs)}")
    print(f"Ảnh đầu vào:     {total_input}")
    print(f"Ảnh được chọn:   {total_selected}")
    print(f"Tỉ lệ giữ lại:   {total_selected / max(total_input, 1):.2%}")
    print(f"Output:          {output_root}")
    print(f"Danh sách chọn:  {output_root / 'selected_images.csv'}")
    print(f"Báo cáo lọc:     {output_root / 'filter_report.csv'}")

    filtered_metadata = output_root / "filtered_metadata.csv"
    if filtered_metadata.is_file():
        print(f"Metadata lọc:    {filtered_metadata}")


if __name__ == "__main__":
    main()