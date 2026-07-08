import cv2
from ultralytics import YOLO
from pathlib import Path
import glob

ROOT = Path(__file__).parents[0].resolve()
MODEL = YOLO(r"E:\Detection_Model_Football\best.pt")


def get_image(image_path):
    imgs_path = glob.glob(f"{ROOT / image_path}/*.jpg")
    return imgs_path



def crop_player(image):
    result = MODEL.predict(image, imgsz=960, conf=0.5)
    xyxy_boxes = result[0].boxes.xyxy.cpu().numpy()
    for box in xyxy_boxes:
        x1, y1, x2, y2 = map(int, box)
        cropped_image = image[y1:y2, x1:x2]
        cv2.imwrite("Cropped Player.jpg", cropped_image)
        break


def main():
    image_paths = get_image(r"yolo_data\train\images")
    for image_path in image_paths:
        print(image_path)
        image = cv2.imread(image_path)
        crop_player(image)
        break


if __name__ == "__main__":
    main()