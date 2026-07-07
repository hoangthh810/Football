import glob
from pathlib import Path
import os
import shutil
import cv2

ROOT = Path(__file__).parents[0]
IMGS_ROOT = ROOT
LABELS_ROOT = ROOT


def get_images_per_5_frames(imgs_root, train=True) -> list:
    if train:
        imgs_path = glob.glob(f"{imgs_root}/train/*/img1/*")
    else:
        imgs_path = glob.glob(f"{imgs_root}/val/*/img1/*")

    imgs_5_path = []

    for img in imgs_path:
        frame_id = int(Path(img).stem)

        # Lấy frame 1, 5, 10, 15, ...
        if frame_id % 5 == 0 or frame_id == 1:
            imgs_5_path.append(img)

    return imgs_5_path


def get_tracklet_class_map(sequence_dir: Path) -> dict:
    """
    Đọc các file .ini/.txt trong từng sequence để map:
    trackletID_x -> class_id

    class:
    0 = player
    1 = referee
    2 = ball
    """

    tracklet_class_map = {}

    info_files = list(sequence_dir.glob("*.ini")) + list(sequence_dir.glob("*.txt"))

    for info_file in info_files:
        # Không đọc gt.txt vì gt.txt là bbox
        if info_file.name.lower() == "gt.txt":
            continue

        try:
            with open(info_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception:
            continue

        for line in lines:
            line = line.strip()

            if not line.lower().startswith("trackletid_"):
                continue

            # Ví dụ:
            # trackletID_18= referee;main
            # trackletID_19= ball;1
            try:
                left, right = line.split("=", 1)
            except ValueError:
                continue

            track_id_text = left.lower().replace("trackletid_", "").strip()

            try:
                track_id = int(track_id_text)
            except ValueError:
                continue

            desc = right.strip().lower()

            if desc.startswith("player"):
                class_id = 0
            elif desc.startswith("goalkeeper") or desc.startswith("goalkeepers"):
                class_id = 0
            elif desc.startswith("referee"):
                class_id = 1
            elif desc.startswith("ball"):
                class_id = 2
            else:
                # Nếu có loại khác thì bỏ qua
                continue

            tracklet_class_map[track_id] = class_id

    return tracklet_class_map


def get_labels_per_5_frames(labels_root, train=True) -> dict:
    if train:
        labels_path = glob.glob(f"{labels_root}/train/*/gt/gt.txt")
    else:
        labels_path = glob.glob(f"{labels_root}/val/*/gt/gt.txt")

    label_5_frames = {}

    for gt_file in labels_path:
        gt_file = Path(gt_file)

        sequence_dir = gt_file.parent.parent
        sequence_name = sequence_dir.name

        tracklet_class_map = get_tracklet_class_map(sequence_dir)

        print(sequence_name, "tracklet map:", tracklet_class_map)

        with open(gt_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line in lines:
            parts = line.strip().split(",")

            if len(parts) < 6:
                continue

            frame_id = int(parts[0])
            object_id = int(parts[1])

            # Lấy frame 1, 5, 10, 15, ...
            if not (frame_id % 5 == 0 or frame_id == 1):
                continue

            # Nếu object_id không tìm thấy trong metadata thì bỏ qua
            # để tránh gán nhầm class.
            if object_id not in tracklet_class_map:
                continue

            class_id = tracklet_class_map[object_id]

            frame_stem = f"{frame_id:06d}"
            label_key = f"{sequence_name}_{frame_stem}"

            if label_key not in label_5_frames:
                label_5_frames[label_key] = []

            # MOT format: frame, id, x, y, width, height, ...
            x = float(parts[2])
            y = float(parts[3])
            width = float(parts[4])
            height = float(parts[5])

            label_5_frames[label_key].append([class_id, x, y, width, height])

    return label_5_frames


def create_data_yolo(name_folder: str, train: bool = True):
    folder_path = Path(name_folder).resolve()

    if train:
        folder_path = folder_path / "train"
    else:
        folder_path = folder_path / "val"

    images_out = folder_path / "images"
    labels_out = folder_path / "labels"

    os.makedirs(images_out, exist_ok=True)
    os.makedirs(labels_out, exist_ok=True)

    imgs = get_images_per_5_frames(IMGS_ROOT, train=train)
    labels = get_labels_per_5_frames(LABELS_ROOT, train=train)

    print("Total images:", len(imgs))

    for img in imgs:
        img_path = Path(img)
        sequence_name = img_path.parent.parent.name
        new_stem = f"{sequence_name}_{img_path.stem}"

        img_cv = cv2.imread(str(img_path))

        if img_cv is None:
            print("Không đọc được ảnh:", img_path)
            continue

        img_h, img_w = img_cv.shape[:2]

        shutil.copy(img_path, images_out / f"{new_stem}{img_path.suffix}")

        label_data = labels.get(new_stem, [])

        with open(labels_out / f"{new_stem}.txt", "w", encoding="utf-8") as f:
            for label in label_data:
                class_id, x, y, width, height = label

                # Cắt bbox nếu vượt ngoài ảnh
                x1 = max(0, x)
                y1 = max(0, y)
                x2 = min(img_w, x + width)
                y2 = min(img_h, y + height)

                box_w = x2 - x1
                box_h = y2 - y1

                if box_w <= 1 or box_h <= 1:
                    continue

                # Convert MOT pixel bbox sang YOLO normalized
                x_center = (x1 + box_w / 2) / img_w
                y_center = (y1 + box_h / 2) / img_h
                w_norm = box_w / img_w
                h_norm = box_h / img_h

                if not (0 <= x_center <= 1 and 0 <= y_center <= 1):
                    continue

                if not (0 < w_norm <= 1 and 0 < h_norm <= 1):
                    continue

                f.write(
                    f"{class_id} {x_center:.6f} {y_center:.6f} {w_norm:.6f} {h_norm:.6f}\n"
                )


create_data_yolo("yolo_data", train=True)
create_data_yolo("yolo_data", train=False)
