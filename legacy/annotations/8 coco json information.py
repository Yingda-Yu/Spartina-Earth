import json

# 你的 COCO JSON 文件路径
ann_file = r"D:\Spatina Test\cocojson.json"

# 读取 JSON 文件
with open(ann_file, "r", encoding="utf-8") as f:
    coco_data = json.load(f)

# 打印 COCO JSON 的键（顶层结构）
print("COCO JSON 顶层结构:", coco_data.keys())

# 查看 `images` 部分的第一个数据
print("\n第一张图片的信息:")
print(json.dumps(coco_data["images"][0], indent=4, ensure_ascii=False))

# 查看 `annotations` 部分的第一个数据
print("\n第一个标注的信息:")
print(json.dumps(coco_data["annotations"][0], indent=4, ensure_ascii=False))

# 查看类别信息
print("\n类别信息:")
print(json.dumps(coco_data["categories"], indent=4, ensure_ascii=False))
