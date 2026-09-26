import os
import cv2

# 图像文件夹路径
image_folder = r"D:\Spatina Test"

# 存储所有图像的尺寸
image_sizes = []

# 遍历文件夹中的所有图像文件
for filename in os.listdir(image_folder):
    if filename.endswith(".jpg"):  # 只处理 .jpg 文件
        image_path = os.path.join(image_folder, filename)

        # 读取图像
        image = cv2.imread(image_path)

        # 获取图像的原始尺寸
        height, width, channels = image.shape
        image_sizes.append((filename, width, height))
        print(f"图像: {filename}, 宽度: {width}, 高度: {height}")

# 可以根据需要选择如何处理所有图像的尺寸
# 比如，你可以计算出最大宽度和最大高度，或者找出最常见的尺寸
max_width = max(image_sizes, key=lambda x: x[1])[1]
max_height = max(image_sizes, key=lambda x: x[2])[2]

print(f"文件夹中的最大图像尺寸: 宽度={max_width}, 高度={max_height}")

# 例如，如果想将所有图像调整为最大尺寸：
# target_width = max_width
# target_height = max_height
