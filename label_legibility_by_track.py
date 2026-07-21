from __future__ import annotations

import argparse
import csv
import random
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VALID_LABELS = {"legible", "not_legible", "skip"}


@dataclass(frozen=True)
class Sample:
    sequence: str
    track: str
    image_path: Path


def find_track_dirs(input_root: Path) -> list[Path]:
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


def select_samples(
    input_root: Path,
    max_per_track: int,
    shuffle_tracks: bool,
    shuffle_images: bool,
    seed: int,
) -> list[Sample]:
    rng = random.Random(seed)
    track_dirs = find_track_dirs(input_root)

    if shuffle_tracks:
        rng.shuffle(track_dirs)

    samples: list[Sample] = []

    for track_dir in track_dirs:
        image_paths = list_images(track_dir)

        if shuffle_images:
            rng.shuffle(image_paths)

        if max_per_track > 0:
            image_paths = image_paths[:max_per_track]

        for image_path in image_paths:
            samples.append(
                Sample(
                    sequence=track_dir.parent.name,
                    track=track_dir.name,
                    image_path=image_path.resolve(),
                )
            )

    return samples


def load_existing_labels(csv_path: Path) -> dict[str, dict[str, str]]:
    """
    Key là đường dẫn tuyệt đối source_path.
    """
    if not csv_path.is_file():
        return {}

    labels: dict[str, dict[str, str]] = {}

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            source_path = row.get("source_path", "").strip()
            label = row.get("label", "").strip()

            if source_path and label in VALID_LABELS:
                labels[str(Path(source_path).resolve())] = row

    return labels


def write_all_labels(
    csv_path: Path,
    rows_by_source: dict[str, dict[str, str]],
) -> None:
    fieldnames = [
        "sequence",
        "track",
        "image_name",
        "label",
        "source_path",
        "output_path",
        "labeled_at",
    ]

    sorted_rows = sorted(
        rows_by_source.values(),
        key=lambda row: (
            row["sequence"],
            row["track"],
            row["image_name"],
        ),
    )

    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted_rows)


def count_labels(
    rows_by_source: dict[str, dict[str, str]],
) -> dict[str, int]:
    counts = {
        "legible": 0,
        "not_legible": 0,
        "skip": 0,
    }

    for row in rows_by_source.values():
        label = row.get("label", "")
        if label in counts:
            counts[label] += 1

    return counts


def create_display(
    image: np.ndarray,
    sample: Sample,
    index: int,
    total: int,
    track_index: int,
    track_total: int,
    counts: dict[str, int],
    target_legible: int,
    target_not_legible: int,
    max_window_width: int,
    max_window_height: int,
) -> np.ndarray:
    """
    Resize ảnh nhưng không làm méo, sau đó thêm bảng thông tin bên phải.
    """
    image_height, image_width = image.shape[:2]

    info_width = 430
    available_width = max(300, max_window_width - info_width)
    available_height = max(300, max_window_height)

    scale = min(
        available_width / image_width,
        available_height / image_height,
        1.0,
    )

    new_width = max(1, int(round(image_width * scale)))
    new_height = max(1, int(round(image_height * scale)))

    resized = cv2.resize(
        image,
        (new_width, new_height),
        interpolation=cv2.INTER_AREA,
    )

    canvas_height = max(new_height, 620)
    canvas_width = new_width + info_width

    canvas = np.full(
        (canvas_height, canvas_width, 3),
        245,
        dtype=np.uint8,
    )
    canvas[:new_height, :new_width] = resized

    panel_x = new_width + 20
    y = 35

    def put(
        text: str,
        font_scale: float = 0.62,
        thickness: int = 1,
        gap: int = 30,
    ) -> None:
        nonlocal y
        cv2.putText(
            canvas,
            text,
            (panel_x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            (20, 20, 20),
            thickness,
            cv2.LINE_AA,
        )
        y += gap

    put("SOCCERNET LEGIBILITY LABELER", 0.68, 2, 40)
    put(f"Sequence: {sample.sequence}")
    put(f"Track:    {sample.track}")
    put(f"Image:    {sample.image_path.name}")
    put(f"Sample:   {index + 1}/{total}")
    put(f"In track: {track_index}/{track_total}")

    y += 12
    put("COUNTS", 0.65, 2, 34)
    put(
        f"Legible:      {counts['legible']}"
        + (
            f"/{target_legible}"
            if target_legible > 0
            else ""
        )
    )
    put(
        f"Not legible:  {counts['not_legible']}"
        + (
            f"/{target_not_legible}"
            if target_not_legible > 0
            else ""
        )
    )
    put(f"Skipped:       {counts['skip']}")

    y += 12
    put("KEYS", 0.65, 2, 34)
    put("1  = LEGIBLE")
    put("2  = NOT LEGIBLE")
    put("3  = SKIP IMAGE")
    put("T  = SKIP REST OF TRACK")
    put("B  = GO BACK")
    put("Q / ESC = SAVE AND QUIT")

    y += 12
    put("LEGIBLE RULE", 0.62, 2, 34)
    put("Read the full number confidently.", 0.50, 1, 25)
    put("Do not infer from track metadata.", 0.50, 1, 25)

    return canvas


def copy_to_label_folder(
    sample: Sample,
    output_root: Path,
    label: str,
) -> Path | None:
    if label == "skip":
        return None

    destination = (
        output_root
        / label
        / sample.sequence
        / sample.track
        / sample.image_path.name
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sample.image_path, destination)
    return destination.resolve()


def delete_old_output(row: dict[str, str]) -> None:
    output_path = row.get("output_path", "").strip()

    if not output_path:
        return

    path = Path(output_path)
    if path.is_file():
        path.unlink()


def get_track_position(
    samples: list[Sample],
    current_index: int,
) -> tuple[int, int]:
    current = samples[current_index]

    same_track_indexes = [
        index
        for index, sample in enumerate(samples)
        if sample.sequence == current.sequence
        and sample.track == current.track
    ]

    try:
        position = same_track_indexes.index(current_index) + 1
    except ValueError:
        position = 1

    return position, len(same_track_indexes)


def targets_reached(
    counts: dict[str, int],
    target_legible: int,
    target_not_legible: int,
) -> bool:
    if target_legible <= 0 or target_not_legible <= 0:
        return False

    return (
        counts["legible"] >= target_legible
        and counts["not_legible"] >= target_not_legible
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Gán nhãn legible/not_legible bằng bàn phím và giữ nguyên "
            "cấu trúc sequence/track."
        )
    )

    parser.add_argument(
        "--input-root",
        type=Path,
        required=True,
        help="Thư mục soccernet_tracklets_filtered.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="Thư mục lưu dataset đã gán nhãn.",
    )
    parser.add_argument(
        "--max-per-track",
        type=int,
        default=3,
        help=(
            "Số ảnh tối đa lấy từ mỗi track. Mặc định 3. "
            "Dùng 0 để lấy toàn bộ."
        ),
    )
    parser.add_argument(
        "--target-legible",
        type=int,
        default=1000,
        help="Dừng khi đạt đủ số ảnh legible và not_legible.",
    )
    parser.add_argument(
        "--target-not-legible",
        type=int,
        default=1000,
        help="Dừng khi đạt đủ số ảnh legible và not_legible.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed để thứ tự ngẫu nhiên được lặp lại khi chạy tiếp.",
    )
    parser.add_argument(
        "--no-shuffle-tracks",
        action="store_true",
        help="Không trộn thứ tự track.",
    )
    parser.add_argument(
        "--no-shuffle-images",
        action="store_true",
        help="Không trộn ảnh bên trong mỗi track.",
    )
    parser.add_argument(
        "--window-width",
        type=int,
        default=1200,
        help="Chiều rộng tối đa cửa sổ.",
    )
    parser.add_argument(
        "--window-height",
        type=int,
        default=820,
        help="Chiều cao tối đa cửa sổ.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    input_root = args.input_root.resolve()
    output_root = args.output_root.resolve()

    if not input_root.is_dir():
        parser.error(f"Không tồn tại input root: {input_root}")

    if input_root == output_root:
        parser.error("--output-root phải khác --input-root")

    output_root.mkdir(parents=True, exist_ok=True)
    labels_csv = output_root / "labels.csv"

    samples = select_samples(
        input_root=input_root,
        max_per_track=args.max_per_track,
        shuffle_tracks=not args.no_shuffle_tracks,
        shuffle_images=not args.no_shuffle_images,
        seed=args.seed,
    )

    if not samples:
        raise FileNotFoundError(
            "Không tìm thấy ảnh trong cấu trúc sequence/track_*."
        )

    rows_by_source = load_existing_labels(labels_csv)
    history: list[tuple[int, str, dict[str, str] | None]] = []

    index = 0
    window_name = "SoccerNet Legibility Labeler"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    while index < len(samples):
        counts = count_labels(rows_by_source)

        if targets_reached(
            counts,
            args.target_legible,
            args.target_not_legible,
        ):
            print("\n[HOÀN TẤT] Đã đạt đủ target hai class.")
            break

        sample = samples[index]
        source_key = str(sample.image_path.resolve())

        # Resume: ảnh đã xử lý thì bỏ qua.
        if source_key in rows_by_source:
            index += 1
            continue

        image = cv2.imread(str(sample.image_path))

        if image is None:
            print(f"[CẢNH BÁO] Không đọc được: {sample.image_path}")
            rows_by_source[source_key] = {
                "sequence": sample.sequence,
                "track": sample.track,
                "image_name": sample.image_path.name,
                "label": "skip",
                "source_path": source_key,
                "output_path": "",
                "labeled_at": datetime.now().isoformat(timespec="seconds"),
            }
            write_all_labels(labels_csv, rows_by_source)
            index += 1
            continue

        track_position, track_total = get_track_position(samples, index)

        display = create_display(
            image=image,
            sample=sample,
            index=index,
            total=len(samples),
            track_index=track_position,
            track_total=track_total,
            counts=counts,
            target_legible=args.target_legible,
            target_not_legible=args.target_not_legible,
            max_window_width=args.window_width,
            max_window_height=args.window_height,
        )

        cv2.imshow(window_name, display)
        key = cv2.waitKey(0) & 0xFF

        if key in (ord("q"), ord("Q"), 27):
            print("\n[ĐÃ LƯU] Dừng theo yêu cầu.")
            break

        if key in (ord("b"), ord("B")):
            if not history:
                print("[THÔNG BÁO] Chưa có thao tác để quay lại.")
                continue

            previous_index, previous_source, previous_old_row = history.pop()
            current_row = rows_by_source.pop(previous_source, None)

            if current_row is not None:
                delete_old_output(current_row)

            if previous_old_row is not None:
                rows_by_source[previous_source] = previous_old_row

            write_all_labels(labels_csv, rows_by_source)
            index = previous_index
            continue

        if key in (ord("t"), ord("T")):
            current_sequence = sample.sequence
            current_track = sample.track

            while (
                index < len(samples)
                and samples[index].sequence == current_sequence
                and samples[index].track == current_track
            ):
                skipped_sample = samples[index]
                skipped_key = str(skipped_sample.image_path.resolve())

                if skipped_key not in rows_by_source:
                    history.append((index, skipped_key, None))
                    rows_by_source[skipped_key] = {
                        "sequence": skipped_sample.sequence,
                        "track": skipped_sample.track,
                        "image_name": skipped_sample.image_path.name,
                        "label": "skip",
                        "source_path": skipped_key,
                        "output_path": "",
                        "labeled_at": datetime.now().isoformat(
                            timespec="seconds"
                        ),
                    }

                index += 1

            write_all_labels(labels_csv, rows_by_source)
            continue

        label: str | None = None

        if key == ord("1"):
            label = "legible"
        elif key == ord("2"):
            label = "not_legible"
        elif key == ord("3"):
            label = "skip"

        if label is None:
            print("[PHÍM KHÔNG HỢP LỆ] Dùng 1, 2, 3, T, B, Q hoặc ESC.")
            continue

        # Không cho vượt quá target của từng class để giữ tập cân bằng.
        current_counts = count_labels(rows_by_source)

        if (
            label == "legible"
            and args.target_legible > 0
            and current_counts["legible"] >= args.target_legible
        ):
            print(
                "[ĐÃ ĐỦ LEGIBLE] Hãy bấm 2 cho not_legible "
                "hoặc 3 để bỏ qua."
            )
            continue

        if (
            label == "not_legible"
            and args.target_not_legible > 0
            and current_counts["not_legible"] >= args.target_not_legible
        ):
            print(
                "[ĐÃ ĐỦ NOT_LEGIBLE] Hãy bấm 1 cho legible "
                "hoặc 3 để bỏ qua."
            )
            continue

        old_row = rows_by_source.get(source_key)
        output_path = copy_to_label_folder(
            sample=sample,
            output_root=output_root,
            label=label,
        )

        row = {
            "sequence": sample.sequence,
            "track": sample.track,
            "image_name": sample.image_path.name,
            "label": label,
            "source_path": source_key,
            "output_path": str(output_path) if output_path else "",
            "labeled_at": datetime.now().isoformat(timespec="seconds"),
        }

        history.append((index, source_key, old_row))
        rows_by_source[source_key] = row
        write_all_labels(labels_csv, rows_by_source)
        index += 1

    cv2.destroyAllWindows()

    final_counts = count_labels(rows_by_source)

    print("\n========== KẾT QUẢ ==========")
    print(f"Legible:      {final_counts['legible']}")
    print(f"Not legible:  {final_counts['not_legible']}")
    print(f"Skipped:       {final_counts['skip']}")
    print(f"Labels CSV:    {labels_csv}")
    print(f"Output folder: {output_root}")


if __name__ == "__main__":
    main()