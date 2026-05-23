from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import sqlite3
import json
import os
import time

app = FastAPI()

DB_PATH = os.path.expanduser("~/mindmap/mindmap.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS maps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '未命名导图',
            data TEXT NOT NULL DEFAULT '{}',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

class MapCreate(BaseModel):
    title: str = "未命名导图"

class MapUpdate(BaseModel):
    title: Optional[str] = None
    data: Optional[str] = None

@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(os.path.dirname(__file__), "index.html"), encoding="utf-8") as f:
        return f.read()

@app.get("/api/maps")
def list_maps():
    conn = get_db()
    rows = conn.execute("SELECT id, title, created_at, updated_at FROM maps ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/maps")
def create_map(body: MapCreate):
    now = int(time.time())
    default_data = json.dumps({
        "id": "root",
        "text": body.title,
        "x": 0, "y": 0,
        "children": []
    })
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO maps (title, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (body.title, default_data, now, now)
    )
    conn.commit()
    map_id = cur.lastrowid
    conn.close()
    return {"id": map_id, "title": body.title, "created_at": now, "updated_at": now}

@app.get("/api/maps/{map_id}")
def get_map(map_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM maps WHERE id=?", (map_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return dict(row)

@app.put("/api/maps/{map_id}")
def update_map(map_id: int, body: MapUpdate):
    conn = get_db()
    row = conn.execute("SELECT * FROM maps WHERE id=?", (map_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Not found")
    now = int(time.time())
    title = body.title if body.title is not None else row["title"]
    data = body.data if body.data is not None else row["data"]
    conn.execute(
        "UPDATE maps SET title=?, data=?, updated_at=? WHERE id=?",
        (title, data, now, map_id)
    )
    conn.commit()
    conn.close()
    return {"id": map_id, "title": title, "updated_at": now}

@app.delete("/api/maps/{map_id}")
def delete_map(map_id: int):
    conn = get_db()
    conn.execute("DELETE FROM maps WHERE id=?", (map_id,))
    conn.commit()
    conn.close()
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8849, reload=False)
