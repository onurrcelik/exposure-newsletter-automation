from fastapi import FastAPI, UploadFile, File, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime
import shutil
from pathlib import Path

from firebase_client import editions_col

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)


# ── Firestore helpers ──────────────────────────────────────────────────────────

def get_edition(edition_id: str) -> dict:
    doc = editions_col().document(edition_id).get()
    if doc.exists:
        return doc.to_dict()
    parts = edition_id.split("_")
    return {
        "edition_id": edition_id,
        "date_from": parts[0],
        "date_to": parts[1] if len(parts) >= 2 else parts[0],
        "created_at": None,
        "files": {},
        "status": "empty",
        "extracted": None,
        "draft": None,
    }


def save_edition(edition_id: str, data: dict):
    editions_col().document(edition_id).set(data, merge=True)


def list_editions() -> list[dict]:
    docs = editions_col().order_by("created_at", direction="DESCENDING").stream()
    return [d.to_dict() for d in docs]


# ── Routes ─────────────────────────────────────────────────────────────────────

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
    (UPLOADS_DIR / edition_id).mkdir(parents=True, exist_ok=True)
    edition = get_edition(edition_id)
    if not edition["created_at"]:
        edition.update({
            "edition_id": edition_id,
            "date_from": date_from,
            "date_to": date_to,
            "created_at": datetime.now().isoformat(),
            "files": {},
            "status": "empty",
            "extracted": None,
            "draft": None,
        })
        save_edition(edition_id, edition)
    return RedirectResponse(f"/edition/{edition_id}", status_code=303)


@app.get("/edition/{edition_id}", response_class=HTMLResponse)
async def edition_detail(request: Request, edition_id: str):
    edition = get_edition(edition_id)
    return templates.TemplateResponse("edition.html", {
        "request": request,
        "edition_id": edition_id,
        "meta": edition,
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

    edition = get_edition(edition_id)
    if not edition["created_at"]:
        edition["created_at"] = datetime.now().isoformat()
    edition.setdefault("files", {})
    edition["files"]["transcript"] = {
        "original_name": file.filename,
        "saved_as": save_name,
        "uploaded_at": datetime.now().isoformat(),
        "size_bytes": dest.stat().st_size,
    }
    edition["status"] = "uploaded" if "whatsapp" in edition["files"] else "partial"
    save_edition(edition_id, edition)

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

    edition = get_edition(edition_id)
    if not edition["created_at"]:
        edition["created_at"] = datetime.now().isoformat()
    edition.setdefault("files", {})
    edition["files"]["whatsapp"] = {
        "original_name": file.filename,
        "saved_as": save_name,
        "uploaded_at": datetime.now().isoformat(),
        "size_bytes": dest.stat().st_size,
    }
    edition["status"] = "uploaded" if "transcript" in edition["files"] else "partial"
    save_edition(edition_id, edition)

    return RedirectResponse(f"/edition/{edition_id}", status_code=303)


@app.post("/edition/{edition_id}/delete")
async def delete_edition(edition_id: str):
    # Delete Firestore document
    editions_col().document(edition_id).delete()
    # Delete uploaded files
    edition_dir = UPLOADS_DIR / edition_id
    if edition_dir.exists():
        shutil.rmtree(edition_dir)
    return RedirectResponse("/", status_code=303)


@app.get("/api/editions")
async def api_editions():
    return list_editions()
