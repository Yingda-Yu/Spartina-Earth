import os
import cv2
import json
import numpy as np

# 文件夹路径和目标尺寸
image_folder = r"D:\Spatina Test"
padded_folder = r"D:\Spatina Test\padded_images"
target_width = 2048
target_height = 1367

# 读取原始 COCO JSON 文件
ann_file = r"D:\Spatina Test\cocojson.json"
with open(ann_file, "r", encoding="utf-8") as f:
    coco_data = json.load(f)

# 创建新的 COCO JSON 数据
new_coco_data = coco_data.copy()

# 创建存储填充后的图像的文件夹（如果不存在的话）
if not os.path.exists(padded_folder):
    os.makedirs(padded_folder)

# 更新图像尺寸，并处理每张图片
new_images = []
for image_info in coco_data["images"]:
    image_path = os.path.join(image_folder, image_info["file_name"])
    if not os.path.exists(image_path):
        continue

    # 读取图像
    image = cv2.imread(image_path)

    # 获取图像的原始尺寸
    height, width, channels = image.shape

    # 计算填充的像素
    top = bottom = (target_height - height) // 2
    left = right = (target_width - width) // 2

    # 填充图像
    padded_image = cv2.copyMakeBorder(image, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(0, 0, 0))

    # 保存填充后的图像
    output_path = os.path.join(padded_folder, image_info["file_name"])
    cv2.imwrite(output_path, padded_image)

    # 更新图像信息
    new_image_info = image_info.copy()
    new_image_info["width"] = target_width
    new_image_info["height"] = target_height
    new_image_info["file_name"] = os.path.basename(output_path)

    new_images.append(new_image_info)

# 更新标注框和分割信息
new_annotations = []
for annotation in coco_data["annotations"]:
    # 获取标注的图像 ID
    image_info = next(item for item in coco_data["images"] if item["id"] == annotation["image_id"])

    # 获取原图像尺寸
    original_width = image_info["width"]
    original_height = image_info["height"]

    # 计算填充的量
    top = bottom = (target_height - original_height) // 2
    left = right = (target_width - original_width) // 2

    # 更新标注的 segmentation 坐标
    new_segmentation = []
    for polygon in annotation["segmentation"]:
        new_polygon = [point + (left if i % 2 == 0 else top) for i, point in enumerate(polygon)]
        new_segmentation.append(new_polygon)

    # 更新标注的 bbox
    x, y, w, h = annotation["bbox"]
    new_bbox = [x + left, y + top, w, h]

    # 创建新的标注
    new_annotation = annotation.copy()
    new_annotation["segmentation"] = new_segmentation
    new_annotation["bbox"] = new_bbox

    new_annotations.append(new_annotation)

# 将新的图像和标注数据加入到 COCO 数据中
new_coco_data["images"] = new_images
new_coco_data["annotations"] = new_annotations

# 保存新的 COCO JSON 文件
new_ann_file = os.path.join(padded_folder, "cocojson_updated.json")
with open(new_ann_file, "w", encoding="utf-8") as f:
    json.dump(new_coco_data, f, ensure_ascii=False, indent=4)

print(f"新的 COCO JSON 文件已保存: {new_ann_file}")
