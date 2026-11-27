import os
import json
import cv2
import numpy as np  # 导入 numpy
import matplotlib.pyplot as plt
from pycocotools.coco import COCO

# 你的 COCO JSON 路径
ann_file = r"D:\Spatina Test\cocojson.json"
image_folder = r"D:\Spatina Test"  # 存储图片的文件夹路径

# 先用 utf-8 读取 JSON 文件并加载到 COCO
with open(ann_file, "r", encoding="utf-8") as f:
    data = json.load(f)

coco = COCO()
coco.dataset = data
coco.createIndex()

# 获取类别信息
categories = coco.loadCats(coco.getCatIds())
category_names = [cat["name"] for cat in categories]

print("类别总数:", len(categories))
print("类别名称:", category_names)

# 获取所有图片 ID
image_ids = coco.getImgIds()

# 计算显示的行列数（在 4 行 5 列的网格中显示图片）
num_images = len(image_ids)
cols = 5
rows = (num_images // cols) + (1 if num_images % cols != 0 else 0)

# 创建一个新的图像窗口显示所有图像
fig, axes = plt.subplots(rows, cols, figsize=(15, rows * 3))  # 创建一个动态大小的网格
axes = axes.flatten()  # 将 2D 的 axes 数组展平，便于后续的循环处理

# 遍历所有图片
for idx, image_id in enumerate(image_ids):
    image_info = coco.loadImgs(image_id)[0]

    # 获取图像路径
    image_path = os.path.join(image_folder, image_info["file_name"])
    if not os.path.exists(image_path):
        print(f"警告: 找不到图像 {image_info['file_name']}")
        continue

    print("正在处理:", image_path)

    # 读取图像
    image = cv2.imread(image_path)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)  # OpenCV 读图是 BGR，需要转换为 RGB

    # 获取该图片的所有标注
    annotation_ids = coco.getAnnIds(imgIds=image_id)
    annotations = coco.loadAnns(annotation_ids)

    # 画出标注框
    for ann in annotations:
        # 如果标注是多边形，则使用 segmentation
        if "segmentation" in ann:
            for polygon in ann["segmentation"]:
                # 绘制多边形
                polygon = np.array(polygon).reshape((-1, 1, 2)).astype(np.int32)
                cv2.polylines(image, [polygon], isClosed=True, color=(255, 0, 0), thickness=2)

    # 将处理后的图像显示在 subplot 网格中
    if idx < len(axes):  # 确保不会超过最大显示图像数
        axes[idx].imshow(image)
        axes[idx].axis("off")
    else:
        print(f"Warning: 超过最大显示图像数, 当前图像 {image_info['file_name']} 被跳过")

# 清空多余的空白子图（即，如果图像不够填满所有子图，就隐藏剩余的子图）
for i in range(num_images, len(axes)):
    axes[i].axis('off')

# 调整显示布局并展示
plt.tight_layout()
plt.show()
