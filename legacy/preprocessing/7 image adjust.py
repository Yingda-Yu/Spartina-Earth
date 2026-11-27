import os
import cv2
import numpy as np

# 图像文件夹路径
image_folder = r"D:\Spatina Test"
padded_folder = r"D:\Spatina Test\padded_images"
target_width = 2048
target_height = 1367

# 遍历文件夹中的所有图像文件
for filename in os.listdir(image_folder):
    if filename.endswith(".jpg"):  # 只处理 .jpg 文件
        image_path = os.path.join(image_folder, filename)

        # 读取图像
        image = cv2.imread(image_path)

        # 获取图像的原始尺寸
        height, width, channels = image.shape

        # 计算目标图像的填充
        top = bottom = (target_height - height) // 2
        left = right = (target_width - width) // 2

        # 如果图像较小，填充它
        if height < target_height or width < target_width:
            # 使用黑色填充
            padded_image = cv2.copyMakeBorder(image, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(0, 0, 0))

            # 保存填充后的图像
            output_path = os.path.join(padded_folder, filename)
            cv2.imwrite(output_path, padded_image)
            print(f"图像 {filename} 已填充至 {target_width}x{target_height} 并保存为 {output_path}")
