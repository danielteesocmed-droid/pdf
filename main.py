import os
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Header, HTTPException
from fastapi.responses import PlainTextResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from pypdf import PdfReader

try:
    from docx import Document as DocxDocument
    DOCX_AVAILABLE = True
except Exception:
    DOCX_AVAILABLE = False

# ---------- config ----------
DATA_DIR = Path(os.getenv("DATA_DIR", "./data")).resolve()
UPLOAD_DIR = DATA_DIR / "files"
TEXT_DIR = DATA_DIR / "text"
META_DIR = DATA_DIR / "meta"
for d in (UPLOAD_DIR, TEXT_DIR, META_DIR):
    d.mkdir(parents=True, exist_ok=True)

API_KEY = os.getenv("API_KEY", "").strip()          # if empty -> open uploads (dev only)
MAX_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))

TEXT_EXT = {".txt", ".md", ".csv", ".json", ".log", ".xml", ".yaml", ".yml", ".html", ".htm"}

app = FastAPI(
    title="DocFetch",
    version="1.0.0",
    description="Upload docs, serve them as plain text for LLM consumption.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- extractors ----------
def extract_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    parts = []
    for i, page in enumerate(reader.pages, 1):
        try:
            t = page.extract_text() or ""
        except Exception as e:
            t = f"[page {i} extraction error: {e}]"
        parts.append(f"\n--- Page {i} ---\n{t}")
    return "".join(parts).strip()

def extract_docx(path: Path) -> str:
    if not DOCX_AVAILABLE:
        raise RuntimeError("python-docx not installed")
    doc = DocxDocument(str(path))
    return "\n".join(p.text for p in doc.paragraphs).strip()

def extract_plain(path: Path) -> str:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_bytes().decode("utf-8", errors="replace")

def extract_text(path: Path, content_type: str, filename: str) -> str:
    ext = Path(filename or path.name).suffix.lower()
    if ext == ".pdf" or "pdf" in (content_type or ""):
        return extract_pdf(path)
    if ext == ".docx" or "wordprocessingml" in (content_type or ""):
        return extract_docx(path)
    if ext in TEXT_EXT or (content_type or "").startswith("text/"):
        return extract_plain(path)
    # last resort: try to sniff as text
    return extract_plain(path)

# ---------- helpers ----------
def require_key(x_api_key: Optional[str]):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")

def doc_paths(doc_id: str):
    meta = META_DIR / f"{doc_id}.json"
    if not meta.exists():
        raise HTTPException(404, "Document not found")
    data = json.loads(meta.read_text(encoding="utf-8"))
    return (
        TEXT_DIR / f"{doc_id}.txt",
        UPLOAD_DIR / f"{doc_id}{data['ext']}",
        meta,
        data,
    )

# ---------- routes ----------
@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!doctype html><html><head><meta charset="utf-8"><title>DocFetch</title>
<style>
body{font-family:system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 16px}
input,button{font-size:1rem;padding:8px}
pre{background:#f4f4f4;padding:12px;overflow:auto;border-radius:6px}
</style></head><body>
<h1>DocFetch</h1>
<p>Upload a document and get back plain-text URLs an LLM can read.</p>
<form id="f">
  <input type="password" id="key" placeholder="X-API-Key (if configured)">
  <input type="file" id="file" required>
  <button type="submit">Upload</button>
</form>
<pre id="out"></pre>
<script>
const f=document.getElementById('f');
f.addEventListener('submit',async e=>{
  e.preventDefault();
  const fd=new FormData();
  fd.append('file',document.getElementById('file').files[0]);
  const r=await fetch('/upload',{method:'POST',headers:{'X-API-Key':document.getElementById('key').value},body:fd});
  document.getElementById('out').textContent=JSON.stringify(await r.json(),null,2);
});
</script>
</body></html>
"""

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/upload")
async def upload(file: UploadFile = File(...), x_api_key: Optional[str] = Header(None)):
    require_key(x_api_key)
    raw = await file.read()
    if len(raw) > MAX_MB * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {MAX_MB} MB")

    doc_id = uuid.uuid4().hex[:12]
    ext = Path(file.filename or "").suffix.lower()
    original = UPLOAD_DIR / f"{doc_id}{ext}"
    original.write_bytes(raw)

    try:
        text = extract_text(original, file.content_type or "", file.filename or "")
        err = None
    except Exception as e:
        text = ""
        err = f"{type(e).__name__}: {e}"

    (TEXT_DIR / f"{doc_id}.txt").write_text(text, encoding="utf-8")

    meta = {
        "id": doc_id,
        "filename": file.filename,
        "content_type": file.content_type,
        "ext": ext,
        "size_bytes": len(raw),
        "chars_extracted": len(text),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "extract_error": err,
        "text_url": f"/doc/{doc_id}",
        "raw_url":  f"/doc/{doc_id}/raw",
        "meta_url": f"/doc/{doc_id}/meta",
    }
    (META_DIR / f"{doc_id}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta

@app.get("/doc/{doc_id}", response_class=PlainTextResponse)
def get_text(doc_id: str, offset: int = 0, limit: int = 0):
    text_path, _, _, _ = doc_paths(doc_id)
    text = text_path.read_text(encoding="utf-8")
    if offset or limit:
        end = offset + limit if limit else None
        text = text[offset:end]
    return PlainTextResponse(text, media_type="text/plain; charset=utf-8")

@app.get("/doc/{doc_id}/raw")
def get_raw(doc_id: str):
    _, raw_path, _, data = doc_paths(doc_id)
    return FileResponse(
        raw_path,
        media_type=data.get("content_type") or "application/octet-stream",
        filename=data.get("filename") or raw_path.name,
    )

@app.get("/doc/{doc_id}/meta")
def get_meta(doc_id: str):
    _, _, meta_path, data = doc_paths(doc_id)
    return data

@app.get("/docs", response_class=PlainTextResponse)
def list_docs():
    """Index of all uploaded docs — handy for LLM discovery."""
    items = []
    for m in sorted(META_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        items.append(json.loads(m.read_text(encoding="utf-8")))
    return PlainTextResponse(json.dumps(items, indent=2), media_type="application/json")

@app.get("/llms.txt", response_class=PlainTextResponse)
def llms_txt():
    """Machine-readable index for LLMs."""
    lines = [
        "# DocFetch",
        "",
        "Public plain-text endpoints for uploaded documents.",
        "",
        "Endpoints:",
        "- GET /docs              → JSON list of all documents",
        "- GET /doc/{id}          → extracted plain text",
        "- GET /doc/{id}?offset=N&limit=M → paginated text",
        "- GET /doc/{id}/raw      → original file",
        "- GET /doc/{id}/meta     → metadata",
        "",
        "Documents:",
    ]
    for m in sorted(META_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        d = json.loads(m.read_text(encoding="utf-8"))
        lines.append(f"- {d['filename']}  →  /doc/{d['id']}")
    return PlainTextResponse("\n".join(lines), media_type="text/plain; charset=utf-8")

@app.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    return "User-agent: *\nAllow: /\n"