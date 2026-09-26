import os
import json
import cv2
import numpy as np
import shutil
import random
from pycocotools.coco import COCO

# 1. 配置路径
coco_json_path = r"D:\Spatina Test\cocojson.json"  # 你的 COCO JSON 文件路径
image_folder = r"D:\Spatina Test"  # 你的图片所在文件夹
output_folder = r"D:\SpartinaDataset"  # 处理后的数据集输出目录

# 2. 创建数据集文件夹
for split in ["train", "val", "test"]:
    os.makedirs(os.path.join(output_folder, split, "images"), exist_ok=True)
    os.makedirs(os.path.join(output_folder, split, "masks"), exist_ok=True)

# 3. 读取 COCO JSON
with open(coco_json_path, "r", encoding="utf-8") as f:
    coco_data = json.load(f)

coco = COCO()
coco.dataset = coco_data
coco.createIndex()

# 4. 获取所有图片 ID 并打乱
image_ids = coco.getImgIds()
random.shuffle(image_ids)

# 5. 计算数据集划分索引
num_images = len(image_ids)
train_split = int(0.7 * num_images)  # 70% 训练集
val_split = int(0.85 * num_images)   # 15% 验证集，15% 测试集

train_ids = image_ids[:train_split]
val_ids = image_ids[train_split:val_split]
test_ids = image_ids[val_split:]

# 6. 处理每张图片，生成 mask 并复制到相应数据集
def process_images(image_ids, split_name):
    for image_id in image_ids:
        image_info = coco.loadImgs(image_id)[0]
        image_path = os.path.join(image_folder, image_info["file_name"])

        # 检查图片是否存在
        if not os.path.exists(image_path):
            print(f"警告: 找不到图片 {image_info['file_name']}")
            continue

        # 读取图片尺寸
        image = cv2.imread(image_path)
        height, width = image.shape[:2]

        # 创建空白 mask
        mask = np.zeros((height, width), dtype=np.uint8)

        # 获取该图片的所有标注
        ann_ids = coco.getAnnIds(imgIds=image_id)
        annotations = coco.loadAnns(ann_ids)

        for ann in annotations:
            if "segmentation" in ann:
                for polygon in ann["segmentation"]:
                    pts = np.array(polygon).reshape((-1, 1, 2)).astype(np.int32)
                    cv2.fillPoly(mask, [pts], 255)  # 目标区域填充 255（白色）

        # 复制图片和 mask 到对应数据集文件夹
        save_img_path = os.path.join(output_folder, split_name, "images", image_info["file_name"])
        save_mask_path = os.path.join(output_folder, split_name, "masks", image_info["file_name"].replace(".jpg", ".png"))

        shutil.copy(image_path, save_img_path)  # 复制原始图片
        cv2.imwrite(save_mask_path, mask)  # 保存 mask

        print(f"已处理: {image_info['file_name']} -> {split_name}")

# 7. 处理所有数据集
process_images(train_ids, "train")
process_images(val_ids, "val")
process_images(test_ids, "test")

print("数据集准备完成！")
