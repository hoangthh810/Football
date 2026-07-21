from __future__ import annotations

import argparse
import csv
import random
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


VALID_LABELS = ("legible", "not_legible")
VALID_SPLITS = ("train", "val", "test")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass(frozen=True)
class Sample:
    label: str
    sequence: str
    track: str
    image_name: str
    source_path: Path


@dataclass(frozen=True)
class GroupStats:
    group_id: str
    legible: int
    not_legible: int

    @property
    def total(self) -> int:
        return self.legible + self.not_legible


def normalize_path(path_text: str) -> Path:
    return Path(path_text.strip().strip('"')).expanduser()


def find_existing_image(
    input_root: Path,
    label: str,
    sequence: str,
    track: str,
    image_name: str,
    output_path_text: str,
    source_path_text: str,
) -> Path | None:
    candidates: list[Path] = []

    if output_path_text:
        candidates.append(normalize_path(output_path_text))

    if sequence and track and image_name:
        candidates.append(
            input_root / label / sequence / track / image_name
        )

    if source_path_text:
        candidates.append(normalize_path(source_path_text))

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    return None


def load_from_labels_csv(input_root: Path) -> list[Sample]:
    labels_csv = input_root / "labels.csv"

    if not labels_csv.is_file():
        return []

    samples: list[Sample] = []
    seen_paths: set[str] = set()

    with labels_csv.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        required_columns = {"label", "sequence", "track", "image_name"}
        actual_columns = set(reader.fieldnames or [])

        missing = required_columns - actual_columns
        if missing:
            raise ValueError(
                "labels.csv thiếu các cột bắt buộc: "
                + ", ".join(sorted(missing))
            )

        for line_number, row in enumerate(reader, start=2):
            label = row.get("label", "").strip()

            if label not in VALID_LABELS:
                continue

            sequence = row.get("sequence", "").strip()
            track = row.get("track", "").strip()
            image_name = row.get("image_name", "").strip()

            if not sequence or not track or not image_name:
                print(
                    f"[CẢNH BÁO] Bỏ dòng {line_number}: "
                    "thiếu sequence/track/image_name."
                )
                continue

            source = find_existing_image(
                input_root=input_root,
                label=label,
                sequence=sequence,
                track=track,
                image_name=image_name,
                output_path_text=row.get("output_path", ""),
                source_path_text=row.get("source_path", ""),
            )

            if source is None:
                print(
                    f"[CẢNH BÁO] Không tìm thấy ảnh ở dòng {line_number}: "
                    f"{sequence}/{track}/{image_name}"
                )
                continue

            source_key = str(source).lower()

            if source_key in seen_paths:
                print(
                    f"[CẢNH BÁO] Bỏ ảnh trùng trong labels.csv: {source}"
                )
                continue

            seen_paths.add(source_key)

            samples.append(
                Sample(
                    label=label,
                    sequence=sequence,
                    track=track,
                    image_name=image_name,
                    source_path=source,
                )
            )

    return samples


def load_from_folders(input_root: Path) -> list[Sample]:
    samples: list[Sample] = []

    for label in VALID_LABELS:
        class_root = input_root / label

        if not class_root.is_dir():
            continue

        for sequence_dir in sorted(class_root.iterdir()):
            if not sequence_dir.is_dir():
                continue

            for track_dir in sorted(sequence_dir.iterdir()):
                if not track_dir.is_dir():
                    continue

                for image_path in sorted(track_dir.iterdir()):
                    if (
                        image_path.is_file()
                        and image_path.suffix.lower() in IMAGE_EXTENSIONS
                    ):
                        samples.append(
                            Sample(
                                label=label,
                                sequence=sequence_dir.name,
                                track=track_dir.name,
                                image_name=image_path.name,
                                source_path=image_path.resolve(),
                            )
                        )

    return samples


def load_samples(input_root: Path) -> list[Sample]:
    samples = load_from_labels_csv(input_root)

    if samples:
        print(
            f"[THÔNG TIN] Đọc {len(samples)} ảnh từ labels.csv."
        )
        return samples

    samples = load_from_folders(input_root)

    if samples:
        print(
            f"[THÔNG TIN] Không dùng được labels.csv; "
            f"đã quét {len(samples)} ảnh từ thư mục."
        )

    return samples


def group_key(sample: Sample, group_by: str) -> str:
    if group_by == "sequence":
        return sample.sequence

    if group_by == "track":
        return f"{sample.sequence}/{sample.track}"

    raise ValueError(f"group_by không hợp lệ: {group_by}")


def build_group_stats(
    samples: Iterable[Sample],
    group_by: str,
) -> list[GroupStats]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)

    for sample in samples:
        counts[group_key(sample, group_by)][sample.label] += 1

    return [
        GroupStats(
            group_id=group_id,
            legible=class_counts["legible"],
            not_legible=class_counts["not_legible"],
        )
        for group_id, class_counts in counts.items()
    ]


def validate_ratios(
    train_ratio: float,
    val_ratio: float,
    test_ratio: float,
) -> dict[str, float]:
    ratios = {
        "train": train_ratio,
        "val": val_ratio,
        "test": test_ratio,
    }

    if any(value <= 0 for value in ratios.values()):
        raise ValueError("Mọi tỉ lệ phải lớn hơn 0.")

    if abs(sum(ratios.values()) - 1.0) > 1e-9:
        raise ValueError(
            "Tổng train-ratio, val-ratio và test-ratio phải bằng 1."
        )

    return ratios


def summarize_assignment(
    assignment: dict[str, str],
    group_stats_map: dict[str, GroupStats],
) -> dict[str, dict[str, int]]:
    summary = {
        split: {
            "groups": 0,
            "legible": 0,
            "not_legible": 0,
            "total": 0,
        }
        for split in VALID_SPLITS
    }

    for group_id, split in assignment.items():
        item = group_stats_map[group_id]
        summary[split]["groups"] += 1
        summary[split]["legible"] += item.legible
        summary[split]["not_legible"] += item.not_legible
        summary[split]["total"] += item.total

    return summary


def assignment_score(
    assignment: dict[str, str],
    group_stats_map: dict[str, GroupStats],
    ratios: dict[str, float],
) -> float:
    summary = summarize_assignment(assignment, group_stats_map)

    total_legible = sum(item.legible for item in group_stats_map.values())
    total_not_legible = sum(
        item.not_legible for item in group_stats_map.values()
    )
    total_images = total_legible + total_not_legible

    score = 0.0

    for split in VALID_SPLITS:
        target_legible = max(total_legible * ratios[split], 1.0)
        target_not_legible = max(
            total_not_legible * ratios[split],
            1.0,
        )
        target_total = max(total_images * ratios[split], 1.0)

        actual = summary[split]

        score += (
            abs(actual["legible"] - target_legible)
            / target_legible
        )
        score += (
            abs(actual["not_legible"] - target_not_legible)
            / target_not_legible
        )
        score += 0.75 * (
            abs(actual["total"] - target_total)
            / target_total
        )

        # Phạt rất mạnh nếu split bị rỗng hoặc thiếu một class.
        if actual["groups"] == 0:
            score += 1000.0

        if actual["legible"] == 0:
            score += 1000.0

        if actual["not_legible"] == 0:
            score += 1000.0

    return score


def generate_random_assignment(
    groups: list[GroupStats],
    ratios: dict[str, float],
    rng: random.Random,
) -> dict[str, str]:
    shuffled = groups[:]
    rng.shuffle(shuffled)

    # Sequence lớn được xử lý trước để dễ cân bằng hơn.
    shuffled.sort(
        key=lambda item: item.total + rng.random() * 0.01,
        reverse=True,
    )

    total_images = sum(item.total for item in groups)
    target_total = {
        split: total_images * ratios[split]
        for split in VALID_SPLITS
    }

    current_total = {split: 0 for split in VALID_SPLITS}
    assignment: dict[str, str] = {}

    # Bảo đảm mỗi split có ít nhất một group.
    initial_splits = list(VALID_SPLITS)
    rng.shuffle(initial_splits)

    for item, split in zip(shuffled[:3], initial_splits):
        assignment[item.group_id] = split
        current_total[split] += item.total

    for item in shuffled[3:]:
        deficits = {
            split: target_total[split] - current_total[split]
            for split in VALID_SPLITS
        }

        max_deficit = max(deficits.values())
        candidates = [
            split
            for split, deficit in deficits.items()
            if abs(deficit - max_deficit) < 1e-9
        ]

        split = rng.choice(candidates)
        assignment[item.group_id] = split
        current_total[split] += item.total

    return assignment


def optimize_assignment(
    groups: list[GroupStats],
    ratios: dict[str, float],
    seed: int,
    trials: int,
) -> tuple[dict[str, str], float]:
    if len(groups) < 3:
        raise ValueError(
            "Cần ít nhất 3 group để chia train/val/test."
        )

    rng = random.Random(seed)
    group_stats_map = {item.group_id: item for item in groups}

    best_assignment: dict[str, str] | None = None
    best_score = float("inf")

    for trial in range(1, trials + 1):
        assignment = generate_random_assignment(
            groups=groups,
            ratios=ratios,
            rng=rng,
        )

        score = assignment_score(
            assignment=assignment,
            group_stats_map=group_stats_map,
            ratios=ratios,
        )

        if score < best_score:
            best_score = score
            best_assignment = assignment.copy()

        if trial % 500 == 0 or trial == trials:
            print(
                f"[TỐI ƯU] Trial {trial}/{trials}, "
                f"best score={best_score:.6f}"
            )

    assert best_assignment is not None
    return best_assignment, best_score


def prepare_output(
    output_root: Path,
    overwrite: bool,
) -> None:
    if output_root.exists() and any(output_root.iterdir()):
        if not overwrite:
            raise FileExistsError(
                f"Output đã có dữ liệu: {output_root}\n"
                "Thêm --overwrite để xóa và tạo lại."
            )

        shutil.rmtree(output_root)

    output_root.mkdir(parents=True, exist_ok=True)


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
            print(
                "[CẢNH BÁO] Không tạo được hardlink, chuyển sang copy: "
                f"{source}"
            )
            shutil.copy2(source, destination)
        return

    raise ValueError(f"mode không hợp lệ: {mode}")


def copy_samples(
    samples: list[Sample],
    assignment: dict[str, str],
    group_by: str,
    output_root: Path,
    mode: str,
) -> list[dict[str, str]]:
    manifest: list[dict[str, str]] = []

    for index, sample in enumerate(samples, start=1):
        group_id = group_key(sample, group_by)
        split = assignment[group_id]

        destination = (
            output_root
            / split
            / sample.label
            / sample.sequence
            / sample.track
            / sample.image_name
        )

        transfer_file(
            source=sample.source_path,
            destination=destination,
            mode=mode,
        )

        manifest.append(
            {
                "split": split,
                "label": sample.label,
                "sequence": sample.sequence,
                "track": sample.track,
                "group_id": group_id,
                "image_name": sample.image_name,
                "source_path": str(sample.source_path),
                "destination_path": str(destination.resolve()),
            }
        )

        if index % 500 == 0 or index == len(samples):
            print(f"[COPY] {index}/{len(samples)} ảnh.")

    return manifest


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
    fieldnames: list[str],
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def verify_no_leakage(
    manifest: list[dict[str, str]],
    group_by: str,
) -> None:
    group_splits: dict[str, set[str]] = defaultdict(set)

    for row in manifest:
        group_splits[row["group_id"]].add(row["split"])

    leaked = {
        group_id: splits
        for group_id, splits in group_splits.items()
        if len(splits) > 1
    }

    if leaked:
        examples = list(leaked.items())[:10]
        raise RuntimeError(
            f"Phát hiện data leakage theo {group_by}: {examples}"
        )

    print(
        f"[KIỂM TRA] Không có leakage theo {group_by}: PASS"
    )


def verify_files_exist(
    manifest: list[dict[str, str]],
) -> None:
    missing = [
        row["destination_path"]
        for row in manifest
        if not Path(row["destination_path"]).is_file()
    ]

    if missing:
        raise RuntimeError(
            "Có file output bị thiếu. Ví dụ: "
            + ", ".join(missing[:5])
        )

    print("[KIỂM TRA] Tất cả file output tồn tại: PASS")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Chia dataset legible/not_legible theo group để tránh "
            "data leakage và giữ phân bố class gần 80/10/10."
        )
    )

    parser.add_argument(
        "--input-root",
        type=Path,
        required=True,
        help="Thư mục legibility_dataset_raw.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="Thư mục output chứa train/val/test.",
    )
    parser.add_argument(
        "--group-by",
        choices=("sequence", "track"),
        default="sequence",
        help=(
            "Mặc định sequence: toàn bộ sequence nằm chung một split. "
            "Track chỉ dùng khi số sequence quá ít."
        ),
    )
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.8,
    )
    parser.add_argument(
        "--val-ratio",
        type=float,
        default=0.1,
    )
    parser.add_argument(
        "--test-ratio",
        type=float,
        default=0.1,
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=10000,
        help=(
            "Số lần tìm cách chia tốt nhất. Mặc định 10000, "
            "dataset nhỏ nên chạy nhanh."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )
    parser.add_argument(
        "--mode",
        choices=("copy", "hardlink"),
        default="copy",
        help=(
            "copy an toàn nhất. hardlink tiết kiệm dung lượng "
            "nếu input/output cùng ổ đĩa."
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Xóa output cũ trước khi chia lại.",
    )

    args = parser.parse_args()

    input_root = args.input_root.resolve()
    output_root = args.output_root.resolve()

    if not input_root.is_dir():
        parser.error(f"Không tồn tại input root: {input_root}")

    if input_root == output_root:
        parser.error("--input-root và --output-root phải khác nhau.")

    if args.trials < 1:
        parser.error("--trials phải >= 1.")

    try:
        ratios = validate_ratios(
            train_ratio=args.train_ratio,
            val_ratio=args.val_ratio,
            test_ratio=args.test_ratio,
        )
        prepare_output(
            output_root=output_root,
            overwrite=args.overwrite,
        )
    except (ValueError, FileExistsError) as error:
        parser.error(str(error))

    samples = load_samples(input_root)

    if not samples:
        raise FileNotFoundError(
            "Không tìm thấy ảnh legible/not_legible hợp lệ."
        )

    class_counts = Counter(sample.label for sample in samples)

    print("\n========== DATASET GỐC ==========")
    print(f"Legible:      {class_counts['legible']}")
    print(f"Not legible:  {class_counts['not_legible']}")
    print(f"Total:        {len(samples)}")

    groups = build_group_stats(
        samples=samples,
        group_by=args.group_by,
    )

    print(f"Groups ({args.group_by}): {len(groups)}")

    assignment, best_score = optimize_assignment(
        groups=groups,
        ratios=ratios,
        seed=args.seed,
        trials=args.trials,
    )

    group_stats_map = {item.group_id: item for item in groups}
    split_stats = summarize_assignment(
        assignment=assignment,
        group_stats_map=group_stats_map,
    )

    manifest = copy_samples(
        samples=samples,
        assignment=assignment,
        group_by=args.group_by,
        output_root=output_root,
        mode=args.mode,
    )

    verify_no_leakage(
        manifest=manifest,
        group_by=args.group_by,
    )
    verify_files_exist(manifest)

    assignment_rows: list[dict[str, object]] = []

    for group_id, split in sorted(assignment.items()):
        item = group_stats_map[group_id]

        assignment_rows.append(
            {
                "group_id": group_id,
                "split": split,
                "legible": item.legible,
                "not_legible": item.not_legible,
                "total": item.total,
            }
        )

    summary_rows: list[dict[str, object]] = []

    for split in VALID_SPLITS:
        stats = split_stats[split]
        summary_rows.append(
            {
                "split": split,
                "num_groups": stats["groups"],
                "legible": stats["legible"],
                "not_legible": stats["not_legible"],
                "total": stats["total"],
                "actual_ratio": round(
                    stats["total"] / len(samples),
                    6,
                ),
                "target_ratio": ratios[split],
            }
        )

    write_csv(
        output_root / "group_assignments.csv",
        assignment_rows,
        [
            "group_id",
            "split",
            "legible",
            "not_legible",
            "total",
        ],
    )

    write_csv(
        output_root / "split_manifest.csv",
        manifest,
        [
            "split",
            "label",
            "sequence",
            "track",
            "group_id",
            "image_name",
            "source_path",
            "destination_path",
        ],
    )

    write_csv(
        output_root / "split_summary.csv",
        summary_rows,
        [
            "split",
            "num_groups",
            "legible",
            "not_legible",
            "total",
            "actual_ratio",
            "target_ratio",
        ],
    )

    print("\n========== KẾT QUẢ CHIA ==========")

    for row in summary_rows:
        print(
            f"{str(row['split']).upper():5s} | "
            f"groups={int(row['num_groups']):3d} | "
            f"legible={int(row['legible']):4d} | "
            f"not_legible={int(row['not_legible']):4d} | "
            f"total={int(row['total']):4d} | "
            f"ratio={float(row['actual_ratio']):.4f}"
        )

    print(f"\nOptimization score: {best_score:.6f}")
    print(f"Output:              {output_root}")
    print(
        f"Summary:             "
        f"{output_root / 'split_summary.csv'}"
    )
    print(
        f"Assignments:         "
        f"{output_root / 'group_assignments.csv'}"
    )
    print(
        f"Manifest:            "
        f"{output_root / 'split_manifest.csv'}"
    )


if __name__ == "__main__":
    main()