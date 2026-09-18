# DocFetch

Upload a PDF/DOCX/TXT/MD/CSV and get back a plain-text URL an LLM can read.

## Deploy on Railway

1. Push this folder to a GitHub repo.
2. Railway → **New Project → Deploy from GitHub repo**.
3. **Variables tab**, add:
   - `API_KEY` — any long random string (protects `/upload`)
   - `MAX_UPLOAD_MB` — e.g. `50`
   - `DATA_DIR` — set to `/data` if you attach a volume (see below)
4. **Volumes tab** (optional but recommended): add a volume mounted at `/data`
   so uploads survive redeploys.
5. Deploy. Railway gives you a public URL like `https://docfetch-production.up.railway.app`.

## Use

Upload:
```bash
curl -X POST https://YOUR-APP.up.railway.app/upload \
  -H "X-API-Key: $API_KEY" \
  -F "file=@26HH0090.pdf"
```

You'll get JSON back with `text_url`, `raw_url`, `meta_url`.

Read as plain text (this is what an LLM fetches):
```bash
curl https://YOUR-APP.up.railway.app/doc/<id>
```

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET  | `/` | none | HTML upload form |
| GET  | `/health` | none | Healthcheck |
| POST | `/upload` | `X-API-Key` | Upload a file |
| GET  | `/doc/{id}` | none | Extracted text (plain, CORS-open) |
| GET  | `/doc/{id}?offset=N&limit=M` | none | Paginated text |
| GET  | `/doc/{id}/raw` | none | Original file |
| GET  | `/doc/{id}/meta` | none | Metadata |
| GET  | `/docs` | none | JSON index of all docs |
| GET  | `/llms.txt` | none | Human/LLM-readable index |