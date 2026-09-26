import os
import time
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 关键词（搜索“互花米草”）
search_query = "Spartina alterniflora"

# 设定下载文件夹
save_dir = "spartina_images"
os.makedirs(save_dir, exist_ok=True)

# 启动 Selenium WebDriver（需安装 ChromeDriver）
options = webdriver.ChromeOptions()
# options.add_argument("--headless")  # 可选，无头模式
driver = webdriver.Chrome(options=options)

# 访问 Google 图片搜索
url = f"https://www.google.com/search?tbm=isch&q={search_query}"
driver.get(url)

# 滚动页面以加载更多图片
for _ in range(5):  # 增加滚动次数
    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.END)
    time.sleep(5)

# 获取所有图片缩略图
image_elements = driver.find_elements(By.CSS_SELECTOR, "img.Q4LuWd")  # Google 图片搜索缩略图的 CSS 选择器

image_urls = []
wait = WebDriverWait(driver, 5)

for i, img in enumerate(image_elements[:50]):  # 限制前50张
    try:
        img.click()  # 点击缩略图，触发右侧高清大图加载
        time.sleep(2)  # 等待高清大图出现

        # 从右侧面板获取高清图 URL
        large_img = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "img.sFlh5c"))
        )
        img_url = large_img.get_attribute("src")

        if img_url.startswith("http"):  # 只添加有效的 HTTP 链接
            image_urls.append(img_url)
            print(f"✅ 获取高清图片: {img_url}")

    except Exception as e:
        print(f"❌ 获取高清图片失败: {e}")

# 关闭浏览器
driver.quit()

# 确保没有重复的 URL
image_urls = list(set(image_urls))

print(f"共找到 {len(image_urls)} 张高清图片，开始下载...")

# 下载图片
for i, url in enumerate(image_urls[:10]):  # 下载最多10张
    try:
        response = requests.get(url, timeout=10)
        with open(os.path.join(save_dir, f"image_{i}.jpg"), "wb") as file:
            file.write(response.content)
        print(f"✅ 下载成功: image_{i}.jpg")
    except Exception as e:
        print(f"❌ 下载失败: {e}")

print("🎉 图片下载完成！")
