import cv2
import json
import matplotlib.pyplot as plt
from pycocotools.coco import COCO
import numpy as np

# 加载新的 COCO JSON 文件
new_ann_file = r"D:\Spatina Test\padded_images\cocojson_updated.json"
with open(new_ann_file, "r", encoding="utf-8") as f:
    coco_data = json.load(f)

# 创建 COCO 对象
coco = COCO()
coco.dataset = coco_data
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
    image_path = r"D:\Spatina Test\padded_images" + '\\' + image_info["file_name"]

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
        elif "bbox" in ann:
            # 如果有 bbox，绘制矩形框
            x, y, w, h = ann["bbox"]
            cv2.rectangle(image, (int(x), int(y)), (int(x + w), int(y + h)), (0, 255, 0), 2)

    # 将处理后的图像显示在 subplot 网格中
    if idx < len(axes):  # 确保不会超过最大显示图像数
        axes[idx].imshow(image)
        axes[idx].axis("off")
    else:
        print(f"Warning: 超过最大显示图像数, 当前图像 {image_info['file_name']} 被跳过")

# 如果有多余的子图（空白位置），隐藏它们
for idx in range(num_images, len(axes)):
    axes[idx].axis("off")

# 调整显示布局并展示
plt.tight_layout()
plt.show()
