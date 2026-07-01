import glob
from pathlib import Path
import os
import shutil

ROOT = Path(__file__).parents[0]
IMGS_ROOT = ROOT / "train"
LABELS_ROOT = ROOT / "train"


def get_images_per_5_frames(IMGS_ROOT) -> list:
    imgs_path = glob.glob(f"{IMGS_ROOT}/SNMOT-060/img1/*")
    imgs_5_path = []
    for img in imgs_path:
        if int(Path(img).stem) % 5 == 0 or int(Path(img).stem) == 1:
            imgs_5_path.append(img)
    return imgs_5_path


def get_labels_per_5_frames(LABELS_ROOT) -> list:
    labels_path = glob.glob(f"{LABELS_ROOT}/SNMOT-060/gt/gt.txt")
    label_5_frames = {}
    with open(labels_path[0], "r") as f:
        lines = f.readlines()
        for line in lines:
            if int(line.split(",")[0]) % 5 == 0 or int(line.split(",")[0]) == 1:
                line = line.strip().split(",")
                if line[0] not in label_5_frames:
                    label_5_frames[line[0]] = []
                track_id = 0
                x = int(line[2])
                y = int(line[3])
                width = int(line[4])
                height = int(line[5])

                label_5_frames[line[0]].append(
                    [
                        track_id,
                        x,
                        y,
                        width,
                        height,
                    ]
                )
    return label_5_frames


def create_data_yolo(name_folder: str, train: bool = True):
    folder_path = Path(name_folder).resolve()
    # if os.path.exists(folder_path) and len(os.listdir(folder_path)) > 0:
    #     raise ValueError(
    #         f"Folder {name_folder} already exists. Please choose a different name.",
    #     )
    if train:
        folder_path = folder_path / "train"
    os.makedirs(f"{folder_path}/images", exist_ok=True)
    os.makedirs(f"{folder_path}/labels", exist_ok=True)
    imgs = get_images_per_5_frames(IMGS_ROOT)
    labels = get_labels_per_5_frames(LABELS_ROOT)

    for img in imgs:
        shutil.copy(img, f"{folder_path}/images/{Path(img).name}")
        break


create_data_yolo("yolo_data", train=True)
