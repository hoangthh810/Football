from __future__ import annotations

import argparse
import configparser
import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import cv2


@dataclass(frozen=True)
class TrackInfo:
    object_type: str
    team: str
    jersey_number: str
    raw_description: str
    raw_identity: str


def read_ini(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    with path.open("r", encoding="utf-8-sig") as file:
        parser.read_file(file)
    return parser


def parse_gameinfo(gameinfo_path: Path) -> dict[int, TrackInfo]:
    """
    Đọc các dòng dạng:
        trackletID_1 = player team left;10
        trackletID_14 = referee;main
        trackletID_18 = ball;1
    """
    parser = read_ini(gameinfo_path)

    if "Sequence" not in parser:
        raise ValueError(f"Không tìm thấy section [Sequence] trong {gameinfo_path}")

    tracks: dict[int, TrackInfo] = {}

    for key, value in parser["Sequence"].items():
        match = re.fullmatch(r"trackletID_(\d+)", key, flags=re.IGNORECASE)
        if not match:
            continue

        track_id = int(match.group(1))
        parts = [part.strip() for part in value.split(";", maxsplit=1)]

        description = parts[0]
        identity = parts[1] if len(parts) == 2 else ""
        description_lower = description.lower()

        # Phải kiểm tra goalkeeper trước player.
        if "goalkeeper" in description_lower:
            object_type = "goalkeeper"
        elif "player" in description_lower:
            object_type = "player"
        elif "referee" in description_lower:
            object_type = "referee"
        elif "ball" in description_lower:
            object_type = "ball"
        else:
            object_type = "other"

        if "team left" in description_lower:
            team = "left"
        elif "team right" in description_lower:
            team = "right"
        else:
            team = "unknown"

        # Nhãn bằng số được xem là số áo. A/B/X/Y... được xem là unknown.
        jersey_number = identity if identity.isdigit() else "unknown"

        tracks[track_id] = TrackInfo(
            object_type=object_type,
            team=team,
            jersey_number=jersey_number,
            raw_description=description,
            raw_identity=identity,
        )

    return tracks


def parse_seqinfo(seqinfo_path: Path) -> dict[str, str]:
    parser = read_ini(seqinfo_path)

    if "Sequence" not in parser:
        raise ValueError(f"Không tìm thấy section [Sequence] trong {seqinfo_path}")

    return dict(parser["Sequence"])


def find_sequence_dirs(dataset_root: Path) -> list[Path]:
    """
    Tìm các thư mục sequence có cấu trúc:
        sequence/
        ├── img1/
        ├── gt/gt.txt
        ├── gameinfo.ini
        └── seqinfo.ini
    """
    sequence_dirs: set[Path] = set()

    for gt_path in dataset_root.rglob("gt.txt"):
        if gt_path.parent.name != "gt":
            continue

        sequence_dir = gt_path.parent.parent

        if (
            (sequence_dir / "gameinfo.ini").is_file()
            and (sequence_dir / "seqinfo.ini").is_file()
        ):
            sequence_dirs.add(sequence_dir.resolve())

    return sorted(sequence_dirs)


def resolve_frame_path(
    image_dir: Path,
    frame_id: int,
    image_ext: str,
) -> Path | None:
    """
    MOT thường dùng tên 000001.jpg. Có thêm fallback cho tên không padding.
    """
    candidates = [
        image_dir / f"{frame_id:06d}{image_ext}",
        image_dir / f"{frame_id:08d}{image_ext}",
        image_dir / f"{frame_id}{image_ext}",
    ]

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    return None


def clamp_bbox(
    x: float,
    y: float,
    width: float,
    height: float,
    image_width: int,
    image_height: int,
    padding_ratio: float,
) -> tuple[int, int, int, int]:
    """
    Chuyển bbox MOT (x, y, width, height) thành xyxy và giới hạn trong ảnh.
    """
    padding_x = width * padding_ratio
    padding_y = height * padding_ratio

    x1 = max(0, int(round(x - padding_x)))
    y1 = max(0, int(round(y - padding_y)))
    x2 = min(image_width, int(round(x + width + padding_x)))
    y2 = min(image_height, int(round(y + height + padding_y)))

    return x1, y1, x2, y2


def process_sequence(
    sequence_dir: Path,
    output_root: Path,
    metadata_writer: csv.DictWriter,
    frame_stride: int,
    min_crop_width: int,
    min_crop_height: int,
    padding_ratio: float,
    only_numbered: bool,
    include_unmapped: bool,
    jpeg_quality: int,
) -> tuple[int, dict[int, int]]:
    seqinfo_path = sequence_dir / "seqinfo.ini"
    gameinfo_path = sequence_dir / "gameinfo.ini"
    gt_path = sequence_dir / "gt" / "gt.txt"

    seqinfo = parse_seqinfo(seqinfo_path)
    track_info = parse_gameinfo(gameinfo_path)

    sequence_name = seqinfo.get("name", sequence_dir.name)
    image_dir_name = seqinfo.get("imDir", "img1")
    image_ext = seqinfo.get("imExt", ".jpg")

    if not image_ext.startswith("."):
        image_ext = f".{image_ext}"

    image_dir = sequence_dir / image_dir_name
    sequence_output = output_root / sequence_name
    sequence_output.mkdir(parents=True, exist_ok=True)

    crop_count = 0
    track_crop_counts: dict[int, int] = defaultdict(int)
    warned_missing_frames: set[int] = set()

    with gt_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)

        for line_number, row in enumerate(reader, start=1):
            if len(row) < 6:
                print(
                    f"[CẢNH BÁO] Bỏ dòng {line_number} trong {gt_path}: "
                    f"cần ít nhất 6 cột."
                )
                continue

            try:
                frame_id = int(float(row[0]))
                track_id = int(float(row[1]))
                x = float(row[2])
                y = float(row[3])
                width = float(row[4])
                height = float(row[5])
                confidence = float(row[6]) if len(row) > 6 else 1.0
            except ValueError:
                print(
                    f"[CẢNH BÁO] Không đọc được số tại dòng {line_number}: {row}"
                )
                continue

            # -1 thường là detection chưa được association, không phải GT track.
            if track_id <= 0:
                continue

            if confidence <= 0:
                continue

            if frame_stride > 1 and (frame_id - 1) % frame_stride != 0:
                continue

            info = track_info.get(track_id)

            if info is None:
                if not include_unmapped:
                    continue

                info = TrackInfo(
                    object_type="unknown",
                    team="unknown",
                    jersey_number="unknown",
                    raw_description="",
                    raw_identity="",
                )
            else:
                # Chỉ lấy cầu thủ và thủ môn, loại referee/ball/other.
                if info.object_type not in {"player", "goalkeeper"}:
                    continue

            if only_numbered and info.jersey_number == "unknown":
                continue

            frame_path = resolve_frame_path(image_dir, frame_id, image_ext)

            if frame_path is None:
                if frame_id not in warned_missing_frames:
                    print(
                        f"[CẢNH BÁO] Không tìm thấy ảnh frame {frame_id} "
                        f"trong {image_dir}"
                    )
                    warned_missing_frames.add(frame_id)
                continue

            image = cv2.imread(str(frame_path))

            if image is None:
                print(f"[CẢNH BÁO] OpenCV không đọc được: {frame_path}")
                continue

            image_height, image_width = image.shape[:2]
            x1, y1, x2, y2 = clamp_bbox(
                x=x,
                y=y,
                width=width,
                height=height,
                image_width=image_width,
                image_height=image_height,
                padding_ratio=padding_ratio,
            )

            crop_width = x2 - x1
            crop_height = y2 - y1

            if crop_width < min_crop_width or crop_height < min_crop_height:
                continue

            crop = image[y1:y2, x1:x2]

            if crop.size == 0:
                continue

            track_dir = sequence_output / f"track_{track_id:04d}"
            track_dir.mkdir(parents=True, exist_ok=True)

            output_path = track_dir / f"frame_{frame_id:06d}.jpg"
            success = cv2.imwrite(
                str(output_path),
                crop,
                [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality],
            )

            if not success:
                print(f"[CẢNH BÁO] Không ghi được ảnh: {output_path}")
                continue

            metadata_writer.writerow(
                {
                    "sequence": sequence_name,
                    "track_id": track_id,
                    "frame_id": frame_id,
                    "object_type": info.object_type,
                    "team": info.team,
                    "jersey_number": info.jersey_number,
                    "raw_identity": info.raw_identity,
                    "bbox_x": x,
                    "bbox_y": y,
                    "bbox_width": width,
                    "bbox_height": height,
                    "crop_x1": x1,
                    "crop_y1": y1,
                    "crop_x2": x2,
                    "crop_y2": y2,
                    "crop_width": crop_width,
                    "crop_height": crop_height,
                    "source_image": str(frame_path.resolve()),
                    "crop_path": str(output_path.resolve()),
                }
            )

            crop_count += 1
            track_crop_counts[track_id] += 1

    return crop_count, dict(track_crop_counts)


def write_track_summary(
    output_root: Path,
    summary_rows: list[dict[str, object]],
) -> None:
    summary_path = output_root / "track_summary.csv"

    fieldnames = [
        "sequence",
        "track_id",
        "object_type",
        "team",
        "jersey_number",
        "raw_identity",
        "num_crops",
    ]

    with summary_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Crop cầu thủ từ SoccerNet MOT ground truth và nhóm ảnh theo "
            "sequence/track_id."
        )
    )

    parser.add_argument(
        "--dataset-root",
        type=Path,
        required=True,
        help="Thư mục gốc chứa các sequence SNMOT-*.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="Thư mục lưu các tracklet đã crop.",
    )
    parser.add_argument(
        "--frame-stride",
        type=int,
        default=1,
        help="Lấy mỗi N frame. Mặc định 1 là lấy toàn bộ.",
    )
    parser.add_argument(
        "--min-crop-width",
        type=int,
        default=10,
        help="Bỏ crop có chiều rộng nhỏ hơn giá trị này.",
    )
    parser.add_argument(
        "--min-crop-height",
        type=int,
        default=20,
        help="Bỏ crop có chiều cao nhỏ hơn giá trị này.",
    )
    parser.add_argument(
        "--padding-ratio",
        type=float,
        default=0.05,
        help="Nới bbox theo tỉ lệ. Ví dụ 0.05 là thêm 5%% mỗi phía.",
    )
    parser.add_argument(
        "--only-numbered",
        action="store_true",
        help="Chỉ giữ track có nhãn số áo dạng số.",
    )
    parser.add_argument(
        "--include-unmapped",
        action="store_true",
        help="Giữ track không xuất hiện trong gameinfo.ini.",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=95,
        choices=range(1, 101),
        metavar="[1-100]",
        help="Chất lượng ảnh JPEG, mặc định 95.",
    )

    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    if args.frame_stride < 1:
        parser.error("--frame-stride phải >= 1")

    if args.padding_ratio < 0:
        parser.error("--padding-ratio phải >= 0")

    dataset_root: Path = args.dataset_root.resolve()
    output_root: Path = args.output_root.resolve()

    if not dataset_root.is_dir():
        parser.error(f"Không tồn tại dataset root: {dataset_root}")

    output_root.mkdir(parents=True, exist_ok=True)

    sequence_dirs = find_sequence_dirs(dataset_root)

    if not sequence_dirs:
        raise FileNotFoundError(
            "Không tìm thấy sequence hợp lệ. Mỗi sequence cần có "
            "img1/, gt/gt.txt, gameinfo.ini và seqinfo.ini."
        )

    metadata_path = output_root / "metadata.csv"
    metadata_fields = [
        "sequence",
        "track_id",
        "frame_id",
        "object_type",
        "team",
        "jersey_number",
        "raw_identity",
        "bbox_x",
        "bbox_y",
        "bbox_width",
        "bbox_height",
        "crop_x1",
        "crop_y1",
        "crop_x2",
        "crop_y2",
        "crop_width",
        "crop_height",
        "source_image",
        "crop_path",
    ]

    total_crops = 0
    total_tracks = 0
    summary_rows: list[dict[str, object]] = []

    with metadata_path.open("w", encoding="utf-8-sig", newline="") as file:
        metadata_writer = csv.DictWriter(file, fieldnames=metadata_fields)
        metadata_writer.writeheader()

        for sequence_index, sequence_dir in enumerate(sequence_dirs, start=1):
            print(
                f"[{sequence_index}/{len(sequence_dirs)}] "
                f"Đang xử lý: {sequence_dir.name}"
            )

            seqinfo = parse_seqinfo(sequence_dir / "seqinfo.ini")
            sequence_name = seqinfo.get("name", sequence_dir.name)
            game_tracks = parse_gameinfo(sequence_dir / "gameinfo.ini")

            crop_count, track_crop_counts = process_sequence(
                sequence_dir=sequence_dir,
                output_root=output_root,
                metadata_writer=metadata_writer,
                frame_stride=args.frame_stride,
                min_crop_width=args.min_crop_width,
                min_crop_height=args.min_crop_height,
                padding_ratio=args.padding_ratio,
                only_numbered=args.only_numbered,
                include_unmapped=args.include_unmapped,
                jpeg_quality=args.jpeg_quality,
            )

            total_crops += crop_count
            total_tracks += len(track_crop_counts)

            for track_id, num_crops in sorted(track_crop_counts.items()):
                info = game_tracks.get(
                    track_id,
                    TrackInfo(
                        object_type="unknown",
                        team="unknown",
                        jersey_number="unknown",
                        raw_description="",
                        raw_identity="",
                    ),
                )

                summary_rows.append(
                    {
                        "sequence": sequence_name,
                        "track_id": track_id,
                        "object_type": info.object_type,
                        "team": info.team,
                        "jersey_number": info.jersey_number,
                        "raw_identity": info.raw_identity,
                        "num_crops": num_crops,
                    }
                )

            print(
                f"    → {len(track_crop_counts)} track, "
                f"{crop_count} crop được lưu."
            )

    write_track_summary(output_root, summary_rows)

    print("\n========== HOÀN TẤT ==========")
    print(f"Sequences: {len(sequence_dirs)}")
    print(f"Tracks:    {total_tracks}")
    print(f"Crops:     {total_crops}")
    print(f"Output:    {output_root}")
    print(f"Metadata:  {metadata_path}")
    print(f"Summary:   {output_root / 'track_summary.csv'}")


if __name__ == "__main__":
    main()
