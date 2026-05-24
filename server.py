from fastapi import FastAPI, HTTPException, Request, Response, Cookie
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
import sqlite3
import json
import os
import time
import hashlib
import secrets

app = FastAPI()

# ── PATHS ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "mindtree.db")
CFG_PATH = os.path.join(BASE_DIR, "config.json")

# ── CONFIG (username / password) ──
def load_config():
    if os.path.exists(CFG_PATH):
        with open(CFG_PATH) as f:
            return json.load(f)
    # Default first-run credentials — user should change via /api/change-password
    cfg = {"username": "admin", "password_hash": _hash("mindtree123")}
    with open(CFG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    return cfg

def save_config(cfg):
    with open(CFG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

# ── SESSION STORE (in-memory, survives restart via token file) ──
SESSIONS: set[str] = set()
SESSION_FILE = os.path.join(BASE_DIR, ".sessions")

def load_sessions():
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE) as f:
            for line in f:
                t = line.strip()
                if t:
                    SESSIONS.add(t)

def save_sessions():
    with open(SESSION_FILE, "w") as f:
        f.write("\n".join(SESSIONS))

load_sessions()

def is_authenticated(token: Optional[str]) -> bool:
    return token is not None and token in SESSIONS

def auth_required(token: Optional[str] = None):
    if not is_authenticated(token):
        raise HTTPException(status_code=401, detail="Unauthorized")

# ── DB ──
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
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
cfg = load_config()

# ── MODELS ──
class LoginBody(BaseModel):
    username: str
    password: str

class ChangePasswordBody(BaseModel):
    old_password: str
    new_password: str

class MapCreate(BaseModel):
    title: str = "未命名导图"

class MapUpdate(BaseModel):
    title: Optional[str] = None
    data: Optional[str] = None

# ── AUTH ROUTES ──
@app.post("/api/login")
def login(body: LoginBody, response: Response):
    global cfg
    cfg = load_config()
    if body.username != cfg["username"] or _hash(body.password) != cfg["password_hash"]:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = secrets.token_hex(32)
    SESSIONS.add(token)
    save_sessions()
    response.set_cookie("mt_token", token, httponly=True, samesite="lax", max_age=30*24*3600)
    return {"ok": True}

@app.post("/api/logout")
def logout(response: Response, mt_token: Optional[str] = Cookie(default=None)):
    if mt_token and mt_token in SESSIONS:
        SESSIONS.discard(mt_token)
        save_sessions()
    response.delete_cookie("mt_token")
    return {"ok": True}

@app.get("/api/auth-check")
def auth_check(mt_token: Optional[str] = Cookie(default=None)):
    return {"ok": is_authenticated(mt_token)}

@app.post("/api/change-password")
def change_password(body: ChangePasswordBody, mt_token: Optional[str] = Cookie(default=None)):
    auth_required(mt_token)
    global cfg
    cfg = load_config()
    if _hash(body.old_password) != cfg["password_hash"]:
        raise HTTPException(status_code=400, detail="原密码错误")
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码至少6位")
    cfg["password_hash"] = _hash(body.new_password)
    save_config(cfg)
    return {"ok": True}

# ── MAIN PAGE ──
@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(BASE_DIR, "index.html"), encoding="utf-8") as f:
        return f.read()

# ── LOGO / FAVICON ──
@app.get("/logo.png")
def serve_logo():
    from fastapi.responses import FileResponse
    p = os.path.join(BASE_DIR, "logo.png")
    if os.path.exists(p):
        return FileResponse(p, media_type="image/png")
    raise HTTPException(status_code=404, detail="logo not found")

@app.get("/favicon.ico")
def favicon():
    from fastapi.responses import FileResponse
    p = os.path.join(BASE_DIR, "logo.png")
    if os.path.exists(p):
        return FileResponse(p, media_type="image/x-icon")
    raise HTTPException(status_code=404)

# ── MAP ROUTES (all protected) ──
@app.get("/api/maps")
def list_maps(mt_token: Optional[str] = Cookie(default=None)):
    auth_required(mt_token)
    conn = get_db()
    rows = conn.execute("SELECT id, title, created_at, updated_at FROM maps ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/maps")
def create_map(body: MapCreate, mt_token: Optional[str] = Cookie(default=None)):
    auth_required(mt_token)
    now = int(time.time())
    default_data = json.dumps({"id": "root", "text": body.title, "x": 0, "y": 0, "children": [], "note": ""})
    conn = get_db()
    cur = conn.execute("INSERT INTO maps (title, data, created_at, updated_at) VALUES (?,?,?,?)", (body.title, default_data, now, now))
    conn.commit()
    mid = cur.lastrowid
    conn.close()
    return {"id": mid, "title": body.title, "created_at": now, "updated_at": now}

@app.get("/api/maps/{map_id}")
def get_map(map_id: int, mt_token: Optional[str] = Cookie(default=None)):
    auth_required(mt_token)
    conn = get_db()
    row = conn.execute("SELECT * FROM maps WHERE id=?", (map_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return dict(row)

@app.put("/api/maps/{map_id}")
def update_map(map_id: int, body: MapUpdate, mt_token: Optional[str] = Cookie(default=None)):
    auth_required(mt_token)
    conn = get_db()
    row = conn.execute("SELECT * FROM maps WHERE id=?", (map_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Not found")
    now = int(time.time())
    title = body.title if body.title is not None else row["title"]
    data  = body.data  if body.data  is not None else row["data"]
    conn.execute("UPDATE maps SET title=?,data=?,updated_at=? WHERE id=?", (title, data, now, map_id))
    conn.commit()
    conn.close()
    return {"id": map_id, "title": title, "updated_at": now}

@app.delete("/api/maps/{map_id}")
def delete_map(map_id: int, mt_token: Optional[str] = Cookie(default=None)):
    auth_required(mt_token)
    conn = get_db()
    conn.execute("DELETE FROM maps WHERE id=?", (map_id,))
    conn.commit()
    conn.close()
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8849, reload=False)
