import glob
from pathlib import Path
import os
import shutil

ROOT = Path(__file__).parents[0]
IMGS_ROOT = ROOT
LABELS_ROOT = ROOT


def get_images_per_5_frames(IMGS_ROOT, train=True) -> list:
    if train:
        imgs_path = glob.glob(f"{IMGS_ROOT}/train/*/img1/*")
    else:
        imgs_path = glob.glob(f"{IMGS_ROOT}/val/*/img1/*")

    imgs_5_path = []

    for img in imgs_path:
        frame_id = int(Path(img).stem)

        if frame_id % 5 == 0 or frame_id == 1:
            imgs_5_path.append(img)

    return imgs_5_path


def get_labels_per_5_frames(LABELS_ROOT, train=True) -> dict:
    if train:
        labels_path = glob.glob(f"{LABELS_ROOT}/train/*/gt/gt.txt")
    else:
        labels_path = glob.glob(f"{LABELS_ROOT}/val/*/gt/gt.txt")

    label_5_frames = {}
    remove_ids = {14, 17, 18, 26}

    for gt_file in labels_path:
        gt_file = Path(gt_file)
        sequence_name = gt_file.parent.parent.name

        with open(gt_file, "r") as f:
            lines = f.readlines()

            for line in lines:
                parts = line.strip().split(",")

                frame_id = int(parts[0])

                if frame_id % 5 == 0 or frame_id == 1:
                    if parts[1] in map(str, remove_ids):  # Loại bỏ các dòng có track_id trong remove_ids
                        continue
                    frame_stem = f"{frame_id:06d}"
                    label_key = f"{sequence_name}_{frame_stem}"

                    if label_key not in label_5_frames:
                        label_5_frames[label_key] = []

                    track_id = 0
                    x = int(parts[2])
                    y = int(parts[3])
                    width = int(parts[4])
                    height = int(parts[5])

                    label_5_frames[label_key].append([track_id, x, y, width, height])

    return label_5_frames


def create_data_yolo(name_folder: str, train: bool = True):
    folder_path = Path(name_folder).resolve()

    if train:
        folder_path = folder_path / "train"
    else:
        folder_path = folder_path / "val"

    os.makedirs(f"{folder_path}/images", exist_ok=True)
    os.makedirs(f"{folder_path}/labels", exist_ok=True)

    imgs = get_images_per_5_frames(IMGS_ROOT, train=train)
    labels = get_labels_per_5_frames(LABELS_ROOT, train=train)

    for img in imgs:
        img_path = Path(img)
        sequence_name = img_path.parent.parent.name

        new_stem = f"{sequence_name}_{img_path.stem}"

        shutil.copy(img_path, f"{folder_path}/images/{new_stem}{img_path.suffix}")

        label_data = labels.get(new_stem, [])

        with open(f"{folder_path}/labels/{new_stem}.txt", "w") as f:
            for label in label_data:
                track_id, x, y, width, height = label
                f.write(f"{track_id} {x} {y} {width} {height}\n")


create_data_yolo("yolo_data", train=True)
create_data_yolo("yolo_data", train=False)
