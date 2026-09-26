import os
import numpy as np
import tensorflow as tf
import cv2
import random
import matplotlib.pyplot as plt
from tensorflow.keras import layers, models

# 设置数据路径
DATA_DIR = "spartina_images"
IMG_SIZE = (224, 224)

# 目标数据集结构
DATASET_DIR = "dataset"
TRAIN_DIR = os.path.join(DATASET_DIR, "train")
VAL_DIR = os.path.join(DATASET_DIR, "val")

# 确保数据集目录存在
os.makedirs(TRAIN_DIR, exist_ok=True)
os.makedirs(VAL_DIR, exist_ok=True)

# 确保分类子目录存在
for subdir in ["spartina", "other"]:
    os.makedirs(os.path.join(TRAIN_DIR, subdir), exist_ok=True)
    os.makedirs(os.path.join(VAL_DIR, subdir), exist_ok=True)

# 处理图片并移动到数据集目录
def preprocess_and_move_images():
    images = os.listdir(DATA_DIR)
    random.shuffle(images)  # 随机打乱数据

    split_ratio = 0.8  # 80% 训练，20% 验证
    split_index = int(len(images) * split_ratio)

    for i, img_name in enumerate(images):
        img_path = os.path.join(DATA_DIR, img_name)
        img = cv2.imread(img_path)

        if img is None:
            continue  # 跳过损坏的图片

        img = cv2.resize(img, IMG_SIZE)  # 调整大小
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)  # 颜色格式转换

        # 确定存储路径
        if i < split_index:
            save_dir = os.path.join(TRAIN_DIR, "spartina")
        else:
            save_dir = os.path.join(VAL_DIR, "spartina")

        cv2.imwrite(os.path.join(save_dir, img_name), img)

    print("✅ 数据预处理完成！")


# 训练 CNN 模型
def train_cnn():
    print("📌 开始训练 CNN...")

    model = models.Sequential([
        layers.Conv2D(32, (3, 3), activation='relu', input_shape=(224, 224, 3)),
        layers.MaxPooling2D(2, 2),
        layers.Conv2D(64, (3, 3), activation='relu'),
        layers.MaxPooling2D(2, 2),
        layers.Conv2D(128, (3, 3), activation='relu'),
        layers.MaxPooling2D(2, 2),
        layers.Flatten(),
        layers.Dense(128, activation='relu'),
        layers.Dense(1, activation='sigmoid')  # 二分类
    ])

    model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])

# 读取数据集
    train_ds = tf.keras.preprocessing.image_dataset_from_directory(
        TRAIN_DIR, image_size=IMG_SIZE, batch_size=32
    )
    val_ds = tf.keras.preprocessing.image_dataset_from_directory(
        VAL_DIR, image_size=IMG_SIZE, batch_size=32
    )

    # 训练模型
    model.fit(train_ds, validation_data=val_ds, epochs=5)

    # 保存模型
    model.save("spartina_model.h5")
    print("✅ CNN 训练完成，模型已保存为 spartina_model.h5")


# 预测测试
def test_model():
    print("📌 加载模型进行测试...")
    model = tf.keras.models.load_model("spartina_model.h5")

    test_images = os.listdir(os.path.join(VAL_DIR, "spartina"))
    if not test_images:
        print("⚠ 没有测试图片！")
        return

    test_img_name = random.choice(test_images)
    test_img_path = os.path.join(VAL_DIR, "spartina", test_img_name)

    img = cv2.imread(test_img_path)
    img_resized = cv2.resize(img, IMG_SIZE)
    img_resized = img_resized / 255.0  # 归一化
    img_resized = np.expand_dims(img_resized, axis=0)  # 增加批次维度

    prediction = model.predict(img_resized)[0][0]
    result = "Spartina (互花米草)" if prediction > 0.5 else "Other (其他)"

    # 显示图片和预测结果
    plt.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    plt.title(f"预测结果: {result}")
    plt.axis("off")
    plt.show()


# 运行整个流程
if __name__ == "__main__":
    preprocess_and_move_images()  # 预处理数据
    train_cnn()  # 训练 CNN
    test_model()  # 测试模型