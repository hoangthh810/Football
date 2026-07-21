from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import torch
import torch.nn as nn
from PIL import ImageOps
from torch.utils.data import DataLoader
from torchvision import datasets, transforms
from torchvision.models import mobilenet_v3_small

try:
    # Torchvision phiên bản mới.
    from torchvision.models import MobileNet_V3_Small_Weights
except ImportError:
    # Tương thích với torchvision cũ hơn.
    MobileNet_V3_Small_Weights = None


CLASS_NAMES_EXPECTED = {"legible", "not_legible"}
IMAGE_NET_MEAN = [0.485, 0.456, 0.406]
IMAGE_NET_STD = [0.229, 0.224, 0.225]


class SquarePad:
    """Thêm padding để ảnh thành hình vuông mà không làm méo cầu thủ."""

    def __init__(self, fill: int = 0) -> None:
        self.fill = fill

    def __call__(self, image):
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


def set_seed(seed: int) -> None:
    """Giúp kết quả có thể lặp lại gần giống nhau."""

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    # Ưu tiên tính lặp lại hơn tốc độ tuyệt đối.
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def build_transforms(image_size: int):
    """
    Train có augmentation nhẹ.
    Val/test chỉ resize và normalize.
    """

    train_transform = transforms.Compose(
        [
            SquarePad(fill=0),
            transforms.Resize((image_size, image_size)),
            transforms.RandomHorizontalFlip(p=0.5),
            transforms.RandomRotation(degrees=5),
            transforms.ColorJitter(
                brightness=0.15,
                contrast=0.15,
                saturation=0.10,
            ),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=IMAGE_NET_MEAN,
                std=IMAGE_NET_STD,
            ),
        ]
    )

    eval_transform = transforms.Compose(
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

    return train_transform, eval_transform


def verify_dataset_structure(
    train_dataset: datasets.ImageFolder,
    val_dataset: datasets.ImageFolder,
    test_dataset: datasets.ImageFolder,
) -> None:
    """Kiểm tra ba split có cùng hai class hay không."""

    train_classes = set(train_dataset.classes)
    val_classes = set(val_dataset.classes)
    test_classes = set(test_dataset.classes)

    if train_classes != CLASS_NAMES_EXPECTED:
        raise ValueError(
            "Train phải có đúng hai class: "
            "legible và not_legible. "
            "Hiện tại: {}".format(train_dataset.classes)
        )

    if val_classes != train_classes or test_classes != train_classes:
        raise ValueError(
            "Train, val và test phải có cùng tên class.\n"
            "Train: {}\nVal: {}\nTest: {}".format(
                train_dataset.classes,
                val_dataset.classes,
                test_dataset.classes,
            )
        )

    if (
        train_dataset.class_to_idx != val_dataset.class_to_idx
        or train_dataset.class_to_idx != test_dataset.class_to_idx
    ):
        raise ValueError(
            "class_to_idx giữa train/val/test không giống nhau."
        )


def build_dataloaders(
    data_root: Path,
    image_size: int,
    batch_size: int,
    num_workers: int,
) -> Tuple[
    Dict[str, datasets.ImageFolder],
    Dict[str, DataLoader],
]:
    train_transform, eval_transform = build_transforms(image_size)

    datasets_by_split = {
        "train": datasets.ImageFolder(
            root=str(data_root / "train"),
            transform=train_transform,
        ),
        "val": datasets.ImageFolder(
            root=str(data_root / "val"),
            transform=eval_transform,
        ),
        "test": datasets.ImageFolder(
            root=str(data_root / "test"),
            transform=eval_transform,
        ),
    }

    verify_dataset_structure(
        datasets_by_split["train"],
        datasets_by_split["val"],
        datasets_by_split["test"],
    )

    pin_memory = torch.cuda.is_available()

    loaders = {
        "train": DataLoader(
            datasets_by_split["train"],
            batch_size=batch_size,
            shuffle=True,
            num_workers=num_workers,
            pin_memory=pin_memory,
        ),
        "val": DataLoader(
            datasets_by_split["val"],
            batch_size=batch_size,
            shuffle=False,
            num_workers=num_workers,
            pin_memory=pin_memory,
        ),
        "test": DataLoader(
            datasets_by_split["test"],
            batch_size=batch_size,
            shuffle=False,
            num_workers=num_workers,
            pin_memory=pin_memory,
        ),
    }

    return datasets_by_split, loaders


def build_model(
    num_classes: int,
    pretrained: bool,
) -> nn.Module:
    """Tạo MobileNetV3-Small và thay lớp cuối thành hai class."""

    if pretrained:
        if MobileNet_V3_Small_Weights is not None:
            model = mobilenet_v3_small(
                weights=MobileNet_V3_Small_Weights.DEFAULT
            )
        else:
            # Dành cho torchvision cũ.
            model = mobilenet_v3_small(pretrained=True)
    else:
        if MobileNet_V3_Small_Weights is not None:
            model = mobilenet_v3_small(weights=None)
        else:
            model = mobilenet_v3_small(pretrained=False)

    input_features = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(input_features, num_classes)

    return model


def set_backbone_trainable(
    model: nn.Module,
    trainable: bool,
) -> None:
    """Đóng băng hoặc mở khóa phần trích xuất đặc trưng."""

    for parameter in model.features.parameters():
        parameter.requires_grad = trainable


def compute_class_weights(
    train_dataset: datasets.ImageFolder,
    device: torch.device,
) -> torch.Tensor:
    """
    Class ít ảnh hơn sẽ được tăng trọng số nhẹ trong CrossEntropyLoss.
    """

    targets = torch.tensor(
        train_dataset.targets,
        dtype=torch.long,
    )

    counts = torch.bincount(
        targets,
        minlength=len(train_dataset.classes),
    ).float()

    if torch.any(counts == 0):
        raise ValueError(
            "Có class không chứa ảnh trong tập train: {}".format(
                counts.tolist()
            )
        )

    weights = counts.sum() / (len(counts) * counts)

    print("Train class counts:", counts.tolist())
    print("Class weights:", weights.tolist())

    return weights.to(device)


def update_confusion_matrix(
    confusion: torch.Tensor,
    targets: torch.Tensor,
    predictions: torch.Tensor,
) -> None:
    targets_cpu = targets.detach().cpu()
    predictions_cpu = predictions.detach().cpu()

    for true_label, predicted_label in zip(
        targets_cpu.tolist(),
        predictions_cpu.tolist(),
    ):
        confusion[true_label, predicted_label] += 1


def metrics_from_confusion(
    confusion: torch.Tensor,
    class_names: List[str],
) -> Dict[str, object]:
    """
    Confusion matrix:
        hàng = nhãn thật
        cột = nhãn dự đoán
    """

    confusion_float = confusion.float()
    total = confusion_float.sum().item()
    correct = confusion_float.diag().sum().item()

    accuracy = correct / total if total > 0 else 0.0

    per_class = {}
    f1_values = []

    for class_index, class_name in enumerate(class_names):
        true_positive = confusion_float[
            class_index,
            class_index,
        ].item()

        predicted_positive = confusion_float[
            :,
            class_index,
        ].sum().item()

        actual_positive = confusion_float[
            class_index,
            :,
        ].sum().item()

        precision = (
            true_positive / predicted_positive
            if predicted_positive > 0
            else 0.0
        )

        recall = (
            true_positive / actual_positive
            if actual_positive > 0
            else 0.0
        )

        f1 = (
            2.0 * precision * recall / (precision + recall)
            if precision + recall > 0
            else 0.0
        )

        f1_values.append(f1)

        per_class[class_name] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": int(actual_positive),
        }

    macro_f1 = (
        sum(f1_values) / len(f1_values)
        if f1_values
        else 0.0
    )

    return {
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "per_class": per_class,
        "confusion_matrix": confusion.tolist(),
    }


def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    num_classes: int,
) -> Tuple[float, Dict[str, object]]:
    model.train()

    running_loss = 0.0
    num_samples = 0
    confusion = torch.zeros(
        (num_classes, num_classes),
        dtype=torch.long,
    )

    for images, targets in loader:
        images = images.to(device, non_blocking=True)
        targets = targets.to(device, non_blocking=True)

        optimizer.zero_grad()

        logits = model(images)
        loss = criterion(logits, targets)

        loss.backward()
        optimizer.step()

        predictions = logits.argmax(dim=1)
        batch_size = targets.size(0)

        running_loss += loss.item() * batch_size
        num_samples += batch_size

        update_confusion_matrix(
            confusion,
            targets,
            predictions,
        )

    average_loss = running_loss / max(num_samples, 1)

    metrics = metrics_from_confusion(
        confusion,
        loader.dataset.classes,
    )

    return average_loss, metrics


@torch.no_grad()
def evaluate(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    num_classes: int,
) -> Tuple[float, Dict[str, object]]:
    model.eval()

    running_loss = 0.0
    num_samples = 0
    confusion = torch.zeros(
        (num_classes, num_classes),
        dtype=torch.long,
    )

    for images, targets in loader:
        images = images.to(device, non_blocking=True)
        targets = targets.to(device, non_blocking=True)

        logits = model(images)
        loss = criterion(logits, targets)

        predictions = logits.argmax(dim=1)
        batch_size = targets.size(0)

        running_loss += loss.item() * batch_size
        num_samples += batch_size

        update_confusion_matrix(
            confusion,
            targets,
            predictions,
        )

    average_loss = running_loss / max(num_samples, 1)

    metrics = metrics_from_confusion(
        confusion,
        loader.dataset.classes,
    )

    return average_loss, metrics


def save_checkpoint(
    path: Path,
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    epoch: int,
    class_to_idx: Dict[str, int],
    image_size: int,
    val_metrics: Dict[str, object],
) -> None:
    torch.save(
        {
            "architecture": "mobilenet_v3_small",
            "epoch": epoch,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "class_to_idx": class_to_idx,
            "image_size": image_size,
            "val_metrics": val_metrics,
        },
        str(path),
    )


def write_history(
    path: Path,
    history: List[Dict[str, object]],
) -> None:
    fieldnames = [
        "epoch",
        "stage",
        "learning_rate",
        "train_loss",
        "train_accuracy",
        "train_macro_f1",
        "val_loss",
        "val_accuracy",
        "val_macro_f1",
        "val_legible_precision",
        "val_legible_recall",
        "val_legible_f1",
    ]

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(history)


def print_metrics(
    title: str,
    loss: float,
    metrics: Dict[str, object],
) -> None:
    legible = metrics["per_class"]["legible"]

    print(
        "{} | loss={:.4f} | acc={:.4f} | "
        "macro_f1={:.4f} | "
        "legible_P={:.4f} | legible_R={:.4f}".format(
            title,
            loss,
            metrics["accuracy"],
            metrics["macro_f1"],
            legible["precision"],
            legible["recall"],
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Train MobileNetV3-Small để phân loại "
            "legible/not_legible."
        )
    )

    parser.add_argument(
        "--data-root",
        type=Path,
        required=True,
        help=(
            "Thư mục chứa train/, val/, test/. "
            "Mỗi split chứa legible/ và not_legible/."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runs_legibility"),
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=20,
    )
    parser.add_argument(
        "--freeze-epochs",
        type=int,
        default=3,
        help=(
            "Số epoch đầu chỉ train classifier. "
            "Sau đó mở backbone để fine-tune."
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
    )
    parser.add_argument(
        "--image-size",
        type=int,
        default=224,
    )
    parser.add_argument(
        "--head-lr",
        type=float,
        default=1e-3,
        help="Learning rate khi backbone đang bị đóng băng.",
    )
    parser.add_argument(
        "--finetune-lr",
        type=float,
        default=1e-4,
        help="Learning rate khi mở toàn bộ model.",
    )
    parser.add_argument(
        "--weight-decay",
        type=float,
        default=1e-4,
    )
    parser.add_argument(
        "--patience",
        type=int,
        default=6,
        help="Early stopping nếu val macro-F1 không cải thiện.",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=0,
        help="Windows nên bắt đầu bằng 0.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )
    parser.add_argument(
        "--no-pretrained",
        action="store_true",
        help="Không dùng trọng số ImageNet pretrained.",
    )

    args = parser.parse_args()

    data_root = args.data_root.resolve()
    output_dir = args.output_dir.resolve()

    if not data_root.is_dir():
        parser.error(
            "Không tồn tại data-root: {}".format(data_root)
        )

    for split in ("train", "val", "test"):
        if not (data_root / split).is_dir():
            parser.error(
                "Thiếu thư mục: {}".format(data_root / split)
            )

    if args.epochs < 1:
        parser.error("--epochs phải >= 1.")

    if args.freeze_epochs < 0:
        parser.error("--freeze-epochs phải >= 0.")

    output_dir.mkdir(parents=True, exist_ok=True)
    set_seed(args.seed)

    device = torch.device(
        "cuda" if torch.cuda.is_available() else "cpu"
    )

    print("Device:", device)
    print("PyTorch:", torch.__version__)

    if device.type == "cuda":
        print("GPU:", torch.cuda.get_device_name(0))

    datasets_by_split, loaders = build_dataloaders(
        data_root=data_root,
        image_size=args.image_size,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
    )

    train_dataset = datasets_by_split["train"]
    val_dataset = datasets_by_split["val"]
    test_dataset = datasets_by_split["test"]

    print("\n========== DATASET ==========")
    print("Classes:", train_dataset.class_to_idx)
    print("Train:", len(train_dataset))
    print("Val:  ", len(val_dataset))
    print("Test: ", len(test_dataset))

    with (output_dir / "class_to_idx.json").open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            train_dataset.class_to_idx,
            file,
            ensure_ascii=False,
            indent=2,
        )

    model = build_model(
        num_classes=len(train_dataset.classes),
        pretrained=not args.no_pretrained,
    )
    model = model.to(device)

    class_weights = compute_class_weights(
        train_dataset,
        device,
    )
    criterion = nn.CrossEntropyLoss(weight=class_weights)

    # Giai đoạn 1: chỉ train classifier.
    if args.freeze_epochs > 0:
        set_backbone_trainable(model, False)
        stage = "frozen_backbone"
        learning_rate = args.head_lr
    else:
        set_backbone_trainable(model, True)
        stage = "finetune_all"
        learning_rate = args.finetune_lr

    optimizer = torch.optim.AdamW(
        filter(
            lambda parameter: parameter.requires_grad,
            model.parameters(),
        ),
        lr=learning_rate,
        weight_decay=args.weight_decay,
    )

    best_val_f1 = -1.0
    epochs_without_improvement = 0
    history: List[Dict[str, object]] = []

    best_model_path = output_dir / "best_model.pth"
    last_model_path = output_dir / "last_model.pth"

    print("\n========== TRAIN ==========")

    for epoch in range(1, args.epochs + 1):
        # Sang giai đoạn fine-tune toàn bộ model.
        if (
            args.freeze_epochs > 0
            and epoch == args.freeze_epochs + 1
        ):
            set_backbone_trainable(model, True)
            stage = "finetune_all"
            learning_rate = args.finetune_lr

            optimizer = torch.optim.AdamW(
                model.parameters(),
                lr=learning_rate,
                weight_decay=args.weight_decay,
            )

            print(
                "\n[MỞ BACKBONE] Fine-tune toàn bộ model "
                "với lr={}".format(learning_rate)
            )

        train_loss, train_metrics = train_one_epoch(
            model=model,
            loader=loaders["train"],
            criterion=criterion,
            optimizer=optimizer,
            device=device,
            num_classes=len(train_dataset.classes),
        )

        val_loss, val_metrics = evaluate(
            model=model,
            loader=loaders["val"],
            criterion=criterion,
            device=device,
            num_classes=len(train_dataset.classes),
        )

        print("\nEpoch {}/{} | stage={}".format(
            epoch,
            args.epochs,
            stage,
        ))
        print_metrics("TRAIN", train_loss, train_metrics)
        print_metrics("VAL  ", val_loss, val_metrics)

        val_legible = val_metrics["per_class"]["legible"]

        history.append(
            {
                "epoch": epoch,
                "stage": stage,
                "learning_rate": learning_rate,
                "train_loss": train_loss,
                "train_accuracy": train_metrics["accuracy"],
                "train_macro_f1": train_metrics["macro_f1"],
                "val_loss": val_loss,
                "val_accuracy": val_metrics["accuracy"],
                "val_macro_f1": val_metrics["macro_f1"],
                "val_legible_precision": val_legible["precision"],
                "val_legible_recall": val_legible["recall"],
                "val_legible_f1": val_legible["f1"],
            }
        )

        write_history(
            output_dir / "history.csv",
            history,
        )

        save_checkpoint(
            path=last_model_path,
            model=model,
            optimizer=optimizer,
            epoch=epoch,
            class_to_idx=train_dataset.class_to_idx,
            image_size=args.image_size,
            val_metrics=val_metrics,
        )

        current_val_f1 = float(val_metrics["macro_f1"])

        if current_val_f1 > best_val_f1:
            best_val_f1 = current_val_f1
            epochs_without_improvement = 0

            save_checkpoint(
                path=best_model_path,
                model=model,
                optimizer=optimizer,
                epoch=epoch,
                class_to_idx=train_dataset.class_to_idx,
                image_size=args.image_size,
                val_metrics=val_metrics,
            )

            print(
                "[SAVE BEST] val macro-F1={:.4f}".format(
                    best_val_f1
                )
            )
        else:
            epochs_without_improvement += 1

            print(
                "[NO IMPROVEMENT] {}/{}".format(
                    epochs_without_improvement,
                    args.patience,
                )
            )

        if epochs_without_improvement >= args.patience:
            print("\n[EARLY STOPPING]")
            break

    print("\n========== TEST BEST MODEL ==========")

    checkpoint = torch.load(
        str(best_model_path),
        map_location=device,
    )
    model.load_state_dict(checkpoint["model_state_dict"])

    test_loss, test_metrics = evaluate(
        model=model,
        loader=loaders["test"],
        criterion=criterion,
        device=device,
        num_classes=len(train_dataset.classes),
    )

    print_metrics("TEST ", test_loss, test_metrics)

    metrics_output = {
        "best_epoch": checkpoint["epoch"],
        "best_val_metrics": checkpoint["val_metrics"],
        "test_loss": test_loss,
        "test_metrics": test_metrics,
        "class_to_idx": train_dataset.class_to_idx,
    }

    with (output_dir / "metrics.json").open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            metrics_output,
            file,
            ensure_ascii=False,
            indent=2,
        )

    confusion = test_metrics["confusion_matrix"]
    class_names = test_dataset.classes

    confusion_lines = [
        "Confusion matrix: hàng = nhãn thật, cột = dự đoán",
        "Class order: {}".format(class_names),
        "",
    ]

    for row in confusion:
        confusion_lines.append(
            " ".join(str(value) for value in row)
        )

    (output_dir / "confusion_matrix.txt").write_text(
        "\n".join(confusion_lines),
        encoding="utf-8",
    )

    print("\n========== HOÀN TẤT ==========")
    print("Best model:", best_model_path)
    print("Last model:", last_model_path)
    print("History:   ", output_dir / "history.csv")
    print("Metrics:   ", output_dir / "metrics.json")
    print(
        "Confusion: ",
        output_dir / "confusion_matrix.txt",
    )


if __name__ == "__main__":
    main()