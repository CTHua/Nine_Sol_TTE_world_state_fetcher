import asyncio
import datetime
import os
import random
import sqlite3
import warnings

import cv2
import discord
import easyocr
import numpy as np
import pytesseract
import requests
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

reader = easyocr.Reader(['en'])

# 忽略特定內容的 warning（pin_memory on MPS）
warnings.filterwarnings("ignore", message="'pin_memory' argument is set as true but not supported on MPS")


load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))

# 連接資料庫（如果檔案不存在會自動建立）
conn = sqlite3.connect("my_database.db")

conn.row_factory = sqlite3.Row

# 建立 cursor 物件
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS state_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    state TEXT,
    activity INTEGER,
    military INTEGER,
    trade INTEGER,
    tech INTEGER,
    culture INTEGER,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")


def insert_state_data(state_data: dict):
    cursor.execute("""
        INSERT INTO state_data (state, activity, influence, military, military_lv, trade, trade_lv, tech, tech_lv, culture, culture_lv)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
        state_data["state"], state_data["activity"], state_data["influence"],
        state_data["military"], state_data["military_lv"],
        state_data["trade"], state_data["trade_lv"],
        state_data["tech"], state_data["tech_lv"],
        state_data["culture"], state_data["culture_lv"]
    ))
    conn.commit()


def check_and_insert_state_data(state_data: dict):
    # 撈出最新一筆
    cursor.execute("""
        SELECT * 
        FROM state_data 
        WHERE state = ?
        ORDER BY updated_at DESC
        LIMIT 1
    """, (state_data["state"],))
    latest_data = cursor.fetchone()

    # 如果沒有資料，就新增
    if not latest_data:
        cursor.execute("""
        INSERT INTO state_data (state, activity, influence, military, military_lv, trade, trade_lv, tech, tech_lv, culture, culture_lv)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            state_data["state"], state_data["activity"], state_data["influence"],
            state_data["military"], state_data["military_lv"],
            state_data["trade"], state_data["trade_lv"],
            state_data["tech"], state_data["tech_lv"],
            state_data["culture"], state_data["culture_lv"]
        ))
        conn.commit()
        return

    # 檢查各項數值是不是有增長
    # 如果軍事、貿易、科技、文化或等級其中一項有增長，就更新
    need_update = False
    for key in ["military", "trade", "tech", "culture"]:
        if latest_data[key] < state_data[key] and state_data[key] - latest_data[key] < 1000:
            need_update = True
            break
        elif latest_data[f"{key}_lv"] < state_data[f"{key}_lv"] and state_data[f"{key}_lv"] - latest_data[f"{key}_lv"] < 10:
            need_update = True
            break
    if latest_data["influence"] < state_data["influence"] and state_data["influence"] - latest_data["influence"] < 10:
        need_update = True
    if latest_data["activity"] != state_data["activity"] and abs(state_data["activity"] - latest_data["activity"]) < 100:
        need_update = True
    if need_update:
        print(f"{state_data['state']} 有增長")
        cursor.execute("""
        INSERT INTO state_data (state, activity, influence, military, military_lv, trade, trade_lv, tech, tech_lv, culture, culture_lv)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            state_data["state"], state_data["activity"], state_data["influence"],
            state_data["military"], state_data["military_lv"],
            state_data["trade"], state_data["trade_lv"],
            state_data["tech"], state_data["tech_lv"],
            state_data["culture"], state_data["culture_lv"]
        ))
        conn.commit()


state_name = {
    "CountryState_Yiguo.png": "夷國",
    "CountryState_Changuo.png": "闡國",
    "CountryState_Yumin.png": "羽民國",
    "CountryState_Xiaguo.png": "夏國",
    "CountryState_Ying.png": "瀛國",
    "CountryState_Yan.png": "奄國",
    "CountryState_Shang.png": "商國",
    "CountryState_GuiFang.png": "鬼方國"
}


class MyClient(discord.Client):
    async def on_ready(self):
        print('Logged on as', self.user)
        await self.read_state_status()
        scheduler = AsyncIOScheduler()
        # 十分鐘爬一次
        scheduler.add_job(self.read_state_status, 'cron', minute='*/3')
        scheduler.start()
        await asyncio.Event().wait()  # 保持事件迴圈運行

    async def read_state_status(self):
        print(f"---- 讀取國家狀態, {datetime.datetime.now()} ----")
        channel = self.get_channel(CHANNEL_ID)  # 將 CHANNEL_ID 替換為目標頻道的 ID
        state_list = []
        async for message in channel.history(limit=10):
            # 讀取訊息裡的圖片
            if message.attachments:
                url = message.attachments[0].url
                state = state_name[url.split("/")[-1].split("?")[0]]
                download_image(url)
                state_list.append(state)
        print(f"抓取 {len(state_list)} 張圖片完畢\n-----------")
        for state in state_list:
            try:
                state_data = get_state_status(state)
                print(f"{state}(影響力: {state_data['influence']}): 活動值: {state_data['activity']}, 軍事值: {state_data['military']}(lv:{state_data['military_lv']}), 貿易值: {state_data['trade']}(lv:{state_data['trade_lv']}), 科技值: {state_data['tech']}(lv:{state_data['tech_lv']}), 文化值: {state_data['culture']}(lv:{state_data['culture_lv']})")
                check_and_insert_state_data(state_data)
            except Exception as e:
                print(f"讀取國家狀態時發生錯誤: {e}")
            print("----")


def download_image(url: str):
    state = state_name[url.split("/")[-1].split("?")[0]]
    response = requests.get(url)
    with open(f"./state_images/{state}.png", "wb") as f:
        f.write(response.content)


def extract_number_from_region(img, x, y, dx, dy):
    # 擷取 ROI 區域
    roi = img[y:y+dy, x:x+dx]

    # 放大 3 倍
    large_img = cv2.resize(roi, dsize=(0, 0), fx=3, fy=3)

    # # 二值化
    # _, thresh = cv2.threshold(large_img, 150, 255, cv2.THRESH_BINARY)

    # # 先腐蝕再膨脹（幫助字元分離）
    # kernel = np.ones((2, 2), np.uint8)
    # processed = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

    # # OCR 辨識（只允許數字、使用單行模式）
    # config = '--psm 7 -c tessedit_char_whitelist=0123456789'
    # text = pytesseract.image_to_string(processed, config=config).strip()

    # 使用 EasyOCR 辨識
    result = reader.readtext(large_img, detail=0)
    return result[0]


def get_state_status(state: str):
    path = f"./state_images/{state}.png"
    img = cv2.imread(path)
    for j in range(0, 450):
        for i in range(0, 800):
            if img[j, i][0] >= 150 or img[j, i][1] >= 150 or img[j, i][2] >= 150:
                img[j, i][0] = 255
                img[j, i][1] = 255
                img[j, i][2] = 255
            else:
                img[j, i][0] = 0
                img[j, i][1] = 0
                img[j, i][2] = 0
    cv2.imwrite(f"./state_images/_{state}_gray.png", img)
    # 讀取圖片
    activity = extract_number_from_region(img, 483, 100, 107, 36)
    military = extract_number_from_region(img, 485, 161, 106, 46)
    military_lv = extract_number_from_region(img, 685, 161, 48, 46)
    trade = extract_number_from_region(img, 485, 224, 106, 46)
    trade_lv = extract_number_from_region(img, 685, 224, 48, 46)
    tech = extract_number_from_region(img, 485, 287, 106, 46)
    tech_lv = extract_number_from_region(img, 685, 287, 48, 46)
    culture = extract_number_from_region(img, 485, 349, 106, 46)
    culture_lv = extract_number_from_region(img, 685, 349, 48, 46)
    influence = extract_number_from_region(img, 85, 288, 52, 50)

    return {
        "state": state,
        "activity": int(activity),
        "influence": int(influence),
        "military": int(military),
        "military_lv": int(military_lv),
        "trade": int(trade),
        "trade_lv": int(trade_lv),
        "tech": int(tech),
        "tech_lv": int(tech_lv),
        "culture": int(culture),
        "culture_lv": int(culture_lv)
    }


client = MyClient()
client.run(TOKEN)
