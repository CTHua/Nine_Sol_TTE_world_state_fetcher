# main.py
from fastapi import FastAPI
import sqlite3
from datetime import datetime, timedelta


app = FastAPI()


@app.get("/")
async def read_root():
    return {"message": "Hello World"}


@app.get("/ping")
async def ping():
    return {"message": "pong"}


@app.get("/state_data")
async def get_state_data():
    conn = sqlite3.connect("my_database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    # 讀取 state_data 各國的最新資料，每個 state 只取一筆
    cursor.execute("""
                    WITH ranked AS (
                    SELECT *,
                            ROW_NUMBER() OVER (PARTITION BY state ORDER BY updated_at DESC) AS rn
                    FROM state_data
                    )
                    SELECT *
                    FROM ranked
                    WHERE rn = 1
                    ORDER BY CASE state
                        WHEN '夷國' THEN 1
                        WHEN '闡國' THEN 2
                        WHEN '羽民國' THEN 3
                        WHEN '夏國' THEN 4
                        WHEN '瀛國' THEN 5
                        WHEN '奄國' THEN 6
                        WHEN '商國' THEN 7
                        WHEN '鬼方國' THEN 8
                        ELSE 999
                    END;
                   """)
    state_data = cursor.fetchall()
    # 移除 id 欄位
    state_data = [dict(row) for row in state_data]

    # 把 state 欄位改成 key
    # 把 updated_at 欄位改成 UTC+8，原本是 UTC 時間
    state_data = {
        row["state"]: {
            "activity": row["activity"],
            "influence": row["influence"],
            "military": row["military"],
            "military_lv": row["military_lv"],
            "trade": row["trade"],
            "trade_lv": row["trade_lv"],
            "tech": row["tech"],
            "tech_lv": row["tech_lv"],
            "culture": row["culture"],
            "culture_lv": row["culture_lv"],
            "updated_at": (datetime.strptime(row["updated_at"], "%Y-%m-%d %H:%M:%S") + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
        }
        for row in state_data
    }
    return state_data


# 輸入 state ，輸出 state 的歷史資料
@app.get("/state_data_history")
async def get_state_data_history(state: str):
    conn = sqlite3.connect("my_database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM state_data WHERE state = ?
        ORDER BY updated_at DESC
    """, (state,))
    state_data = cursor.fetchall()
    return state_data
