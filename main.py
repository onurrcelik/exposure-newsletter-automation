from fastapi import FastAPI, UploadFile, File, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime
import os, json, shutil
from pathlib import Path

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)


def get_edition_meta(edition_id: str) -> dict:
    meta_path = UPLOADS_DIR / edition_id / "meta.json"
    if meta_path.exists():
        data = json.loads(meta_path.read_text())
        # Migrate old format that used "week" key
        if "week" in data and "edition_id" not in data:
            w = data["week"]
            data["edition_id"] = w
            data["date_from"] = w
            data["date_to"] = w
        return data
    # Parse date range from folder name (new format: date_from_date_to)
    parts = edition_id.split("_")
    date_from = parts[0] if len(parts) >= 1 else edition_id
    date_to = parts[1] if len(parts) >= 2 else edition_id
    return {
        "edition_id": edition_id,
        "date_from": date_from,
        "date_to": date_to,
        "created_at": None,
        "files": {},
        "status": "empty",
    }


def save_meta(edition_id: str, meta: dict):
    (UPLOADS_DIR / edition_id).mkdir(parents=True, exist_ok=True)
    meta_path = UPLOADS_DIR / edition_id / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))


def list_editions() -> list[dict]:
    editions = []
    for folder in sorted(UPLOADS_DIR.iterdir(), reverse=True):
        if folder.is_dir() and (folder / "meta.json").exists():
            editions.append(get_edition_meta(folder.name))
    return editions


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    editions = list_editions()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "editions": editions,
    })


@app.post("/edition/create")
async def create_edition(date_from: str = Form(...), date_to: str = Form(...)):
    edition_id = f"{date_from}_{date_to}"
    edition_dir = UPLOADS_DIR / edition_id
    edition_dir.mkdir(parents=True, exist_ok=True)
    meta = get_edition_meta(edition_id)
    if not meta["created_at"]:
        meta["created_at"] = datetime.now().isoformat()
        meta["edition_id"] = edition_id
        meta["date_from"] = date_from
        meta["date_to"] = date_to
        save_meta(edition_id, meta)
    return RedirectResponse(f"/edition/{edition_id}", status_code=303)


@app.get("/edition/{edition_id}", response_class=HTMLResponse)
async def edition_detail(request: Request, edition_id: str):
    meta = get_edition_meta(edition_id)
    return templates.TemplateResponse("edition.html", {
        "request": request,
        "edition_id": edition_id,
        "meta": meta,
    })


@app.post("/upload/{edition_id}/transcript")
async def upload_transcript(edition_id: str, file: UploadFile = File(...)):
    edition_dir = UPLOADS_DIR / edition_id
    edition_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename).suffix or ".txt"
    save_name = f"transcript{suffix}"
    dest = edition_dir / save_name

    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    meta = get_edition_meta(edition_id)
    if not meta["created_at"]:
        meta["created_at"] = datetime.now().isoformat()
    meta["files"]["transcript"] = {
        "original_name": file.filename,
        "saved_as": save_name,
        "uploaded_at": datetime.now().isoformat(),
        "size_bytes": dest.stat().st_size,
    }
    meta["status"] = "uploaded" if "whatsapp" in meta["files"] else "partial"
    save_meta(edition_id, meta)

    return RedirectResponse(f"/edition/{edition_id}", status_code=303)


@app.post("/upload/{edition_id}/whatsapp")
async def upload_whatsapp(edition_id: str, file: UploadFile = File(...)):
    edition_dir = UPLOADS_DIR / edition_id
    edition_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename).suffix or ".zip"
    save_name = f"whatsapp_export{suffix}"
    dest = edition_dir / save_name

    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    meta = get_edition_meta(edition_id)
    if not meta["created_at"]:
        meta["created_at"] = datetime.now().isoformat()
    meta["files"]["whatsapp"] = {
        "original_name": file.filename,
        "saved_as": save_name,
        "uploaded_at": datetime.now().isoformat(),
        "size_bytes": dest.stat().st_size,
    }
    meta["status"] = "uploaded" if "transcript" in meta["files"] else "partial"
    save_meta(edition_id, meta)

    return RedirectResponse(f"/edition/{edition_id}", status_code=303)


@app.get("/api/editions")
async def api_editions():
    return list_editions()
