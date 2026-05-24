from fastapi import FastAPI, HTTPException, Response, Cookie, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Optional
import sqlite3, json, os, time, hashlib, secrets, shutil

app = FastAPI()

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DB_PATH     = os.path.join(BASE_DIR, "mindtree.db")
CFG_PATH    = os.path.join(BASE_DIR, "config.json")
UPLOAD_DIR  = os.path.join(BASE_DIR, "uploads")
SESSION_FILE= os.path.join(BASE_DIR, ".sessions")

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ── CONFIG ──
def load_config():
    if os.path.exists(CFG_PATH):
        with open(CFG_PATH) as f: return json.load(f)
    cfg = {"username": "admin", "password_hash": _hash("mindtree123")}
    with open(CFG_PATH, "w") as f: json.dump(cfg, f, indent=2)
    return cfg

def save_config(cfg):
    with open(CFG_PATH, "w") as f: json.dump(cfg, f, indent=2)

def _hash(pw): return hashlib.sha256(pw.encode()).hexdigest()

# ── SESSIONS ──
SESSIONS: set = set()

def load_sessions():
    if os.path.exists(SESSION_FILE):
        for line in open(SESSION_FILE): SESSIONS.add(line.strip()) if line.strip() else None

def save_sessions():
    open(SESSION_FILE,"w").write("\n".join(SESSIONS))

load_sessions()

def is_auth(token): return token is not None and token in SESSIONS
def require_auth(token):
    if not is_auth(token): raise HTTPException(401, "Unauthorized")

# ── DB ──
def get_db():
    c = sqlite3.connect(DB_PATH); c.row_factory = sqlite3.Row; return c

def init_db():
    c = get_db()
    c.execute("""CREATE TABLE IF NOT EXISTS maps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL DEFAULT '未命名导图',
        data TEXT NOT NULL DEFAULT '{}',
        created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)""")
    c.commit(); c.close()

init_db()
cfg = load_config()

# ── MODELS ──
class LoginBody(BaseModel): username: str; password: str
class ChangePwBody(BaseModel): old_password: str; new_password: str
class MapCreate(BaseModel): title: str = "未命名导图"
class MapUpdate(BaseModel): title: Optional[str]=None; data: Optional[str]=None

# ── AUTH ──
@app.post("/api/login")
def login(body: LoginBody, response: Response):
    global cfg; cfg = load_config()
    if body.username != cfg["username"] or _hash(body.password) != cfg["password_hash"]:
        raise HTTPException(401, "用户名或密码错误")
    token = secrets.token_hex(32)
    SESSIONS.add(token); save_sessions()
    response.set_cookie("mt_token", token, httponly=True, samesite="lax", max_age=30*24*3600)
    return {"ok": True}

@app.post("/api/logout")
def logout(response: Response, mt_token: Optional[str]=Cookie(default=None)):
    SESSIONS.discard(mt_token); save_sessions()
    response.delete_cookie("mt_token"); return {"ok": True}

@app.get("/api/auth-check")
def auth_check(mt_token: Optional[str]=Cookie(default=None)):
    return {"ok": is_auth(mt_token)}

@app.post("/api/change-password")
def change_pw(body: ChangePwBody, mt_token: Optional[str]=Cookie(default=None)):
    require_auth(mt_token); global cfg; cfg = load_config()
    if _hash(body.old_password) != cfg["password_hash"]: raise HTTPException(400, "原密码错误")
    if len(body.new_password) < 6: raise HTTPException(400, "新密码至少6位")
    cfg["password_hash"] = _hash(body.new_password); save_config(cfg)
    return {"ok": True}

# ── STATIC ──
@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(BASE_DIR,"index.html"), encoding="utf-8") as f: return f.read()

@app.get("/logo.png")
def serve_logo():
    p = os.path.join(BASE_DIR, "logo.png")
    if os.path.exists(p): return FileResponse(p, media_type="image/png")
    raise HTTPException(404)

@app.get("/favicon.ico")
def favicon():
    p = os.path.join(BASE_DIR, "logo.png")
    if os.path.exists(p): return FileResponse(p, media_type="image/x-icon")
    raise HTTPException(404)

# ── IMAGE UPLOAD ──
ALLOWED_EXT = {".jpg",".jpeg",".png",".gif",".webp"}
MAX_SIZE = 10 * 1024 * 1024  # 10MB

@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...), mt_token: Optional[str]=Cookie(default=None)):
    require_auth(mt_token)
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXT: raise HTTPException(400, "只支持 JPG/PNG/GIF/WebP")
    data = await file.read()
    if len(data) > MAX_SIZE: raise HTTPException(400, "图片不能超过 10MB")
    fname = secrets.token_hex(12) + ext
    fpath = os.path.join(UPLOAD_DIR, fname)
    with open(fpath, "wb") as f: f.write(data)
    return {"url": f"/uploads/{fname}"}

@app.get("/uploads/{filename}")
def serve_upload(filename: str, mt_token: Optional[str]=Cookie(default=None)):
    require_auth(mt_token)
    # sanitize
    filename = os.path.basename(filename)
    fpath = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(fpath): raise HTTPException(404)
    return FileResponse(fpath)

# ── MAPS ──
@app.get("/api/maps")
def list_maps(mt_token: Optional[str]=Cookie(default=None)):
    require_auth(mt_token)
    c = get_db()
    rows = c.execute("SELECT id,title,created_at,updated_at FROM maps ORDER BY updated_at DESC").fetchall()
    c.close(); return [dict(r) for r in rows]

@app.post("/api/maps")
def create_map(body: MapCreate, mt_token: Optional[str]=Cookie(default=None)):
    require_auth(mt_token)
    now = int(time.time())
    data = json.dumps({"id":"root","text":body.title,"x":0,"y":0,"children":[],"note":"","html":""})
    c = get_db(); cur = c.execute("INSERT INTO maps(title,data,created_at,updated_at) VALUES(?,?,?,?)",(body.title,data,now,now))
    c.commit(); mid=cur.lastrowid; c.close()
    return {"id":mid,"title":body.title,"created_at":now,"updated_at":now}

@app.get("/api/maps/{map_id}")
def get_map(map_id: int, mt_token: Optional[str]=Cookie(default=None)):
    require_auth(mt_token)
    c = get_db(); row = c.execute("SELECT * FROM maps WHERE id=?",(map_id,)).fetchone(); c.close()
    if not row: raise HTTPException(404)
    return dict(row)

@app.put("/api/maps/{map_id}")
def update_map(map_id: int, body: MapUpdate, mt_token: Optional[str]=Cookie(default=None)):
    require_auth(mt_token)
    c = get_db(); row = c.execute("SELECT * FROM maps WHERE id=?",(map_id,)).fetchone()
    if not row: c.close(); raise HTTPException(404)
    now=int(time.time())
    title = body.title if body.title is not None else row["title"]
    data  = body.data  if body.data  is not None else row["data"]
    c.execute("UPDATE maps SET title=?,data=?,updated_at=? WHERE id=?",(title,data,now,map_id))
    c.commit(); c.close(); return {"id":map_id,"title":title,"updated_at":now}

@app.delete("/api/maps/{map_id}")
def delete_map(map_id: int, mt_token: Optional[str]=Cookie(default=None)):
    require_auth(mt_token)
    c = get_db(); c.execute("DELETE FROM maps WHERE id=?",(map_id,)); c.commit(); c.close()
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8849, reload=False)
