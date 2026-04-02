from fastapi import FastAPI, UploadFile, File, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import date, timedelta
import os, json, shutil
from pathlib import Path

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)


def current_week_monday() -> str:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


def get_week_meta(week_date: str) -> dict:
    meta_path = UPLOADS_DIR / week_date / "meta.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text())
    return {
        "week": week_date,
        "created_at": None,
        "files": {},
        "status": "empty",
    }


def save_meta(week_date: str, meta: dict):
    (UPLOADS_DIR / week_date).mkdir(parents=True, exist_ok=True)
    meta_path = UPLOADS_DIR / week_date / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))


def list_weeks() -> list[dict]:
    weeks = []
    for folder in sorted(UPLOADS_DIR.iterdir(), reverse=True):
        if folder.is_dir() and (folder / "meta.json").exists():
            weeks.append(get_week_meta(folder.name))
    return weeks


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    weeks = list_weeks()
    current_week = current_week_monday()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "weeks": weeks,
        "current_week": current_week,
    })


@app.post("/week/create")
async def create_week(week_date: str = Form(...)):
    week_dir = UPLOADS_DIR / week_date
    week_dir.mkdir(parents=True, exist_ok=True)
    meta = get_week_meta(week_date)
    if not meta["created_at"]:
        from datetime import datetime
        meta["created_at"] = datetime.now().isoformat()
        save_meta(week_date, meta)
    return RedirectResponse(f"/week/{week_date}", status_code=303)


@app.get("/week/{week_date}", response_class=HTMLResponse)
async def week_detail(request: Request, week_date: str):
    meta = get_week_meta(week_date)
    return templates.TemplateResponse("week.html", {
        "request": request,
        "week_date": week_date,
        "meta": meta,
    })


@app.post("/upload/{week_date}/transcript")
async def upload_transcript(week_date: str, file: UploadFile = File(...)):
    from datetime import datetime
    week_dir = UPLOADS_DIR / week_date
    week_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename).suffix or ".txt"
    save_name = f"transcript{suffix}"
    dest = week_dir / save_name

    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    meta = get_week_meta(week_date)
    if not meta["created_at"]:
        meta["created_at"] = datetime.now().isoformat()
    meta["files"]["transcript"] = {
        "original_name": file.filename,
        "saved_as": save_name,
        "uploaded_at": datetime.now().isoformat(),
        "size_bytes": dest.stat().st_size,
    }
    meta["status"] = "uploaded" if "whatsapp" in meta["files"] else "partial"
    save_meta(week_date, meta)

    return RedirectResponse(f"/week/{week_date}", status_code=303)


@app.post("/upload/{week_date}/whatsapp")
async def upload_whatsapp(week_date: str, file: UploadFile = File(...)):
    from datetime import datetime
    week_dir = UPLOADS_DIR / week_date
    week_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename).suffix or ".zip"
    save_name = f"whatsapp_export{suffix}"
    dest = week_dir / save_name

    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    meta = get_week_meta(week_date)
    if not meta["created_at"]:
        meta["created_at"] = datetime.now().isoformat()
    meta["files"]["whatsapp"] = {
        "original_name": file.filename,
        "saved_as": save_name,
        "uploaded_at": datetime.now().isoformat(),
        "size_bytes": dest.stat().st_size,
    }
    meta["status"] = "uploaded" if "transcript" in meta["files"] else "partial"
    save_meta(week_date, meta)

    return RedirectResponse(f"/week/{week_date}", status_code=303)


@app.get("/api/weeks")
async def api_weeks():
    return list_weeks()
