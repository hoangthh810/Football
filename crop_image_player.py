import cv2
from ultralytics import YOLO
from pathlib import Path
import glob
import os

ROOT = Path(__file__).parents[0].resolve()
MODEL = YOLO(r"E:\Detection_Model_Football\best.pt")
DESTINATION_FOLDER = ROOT / "cropped_players"
COUNT = 0
os.makedirs(DESTINATION_FOLDER, exist_ok=True)


def get_image(image_path):
    search_path = str(ROOT / image_path / "*.jpg")
    imgs_path = glob.glob(search_path)
    return imgs_path



def crop_player(image):
    global COUNT
    result = MODEL.predict(image, imgsz=960, conf=0.5)
    xyxy_boxes = result[0].boxes.xyxy.cpu().numpy()
    class_ids = result[0].boxes.cls.cpu().numpy()
    REFEREE_CLASS_ID = 1
    BALL_CLASS_ID = 2
    for box, cls_id in zip(xyxy_boxes, class_ids):
        if int(cls_id) == REFEREE_CLASS_ID or int(cls_id) == BALL_CLASS_ID:
            continue
        x1, y1, x2, y2 = map(int, box)
        cropped_image = image[y1:y2, x1:x2]
        if cropped_image.size > 0:
            file_name = f"crop_player_{COUNT}.jpg"
            save_path = str(DESTINATION_FOLDER / file_name)
            success = cv2.imwrite(save_path, cropped_image)
            if success:
                COUNT += 1
            else:
                print(f"[LỖI] Không thể ghi ảnh vào: {save_path}")    


def main():
    image_paths = get_image(r"yolo_data\train\images")
    sampled_image_paths_5 = image_paths[::10]
    for image_path in sampled_image_paths_5:
        image = cv2.imread(image_path)
        crop_player(image)
    print(f"[THÀNH CÔNG] Đã cắt {COUNT} ảnh cầu thủ và lưu vào thư mục: {DESTINATION_FOLDER}")

if __name__ == "__main__":
    main()