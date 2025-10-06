# pdf2htmlEX (light)

Service FastAPI minimal pour convertir un PDF en HTML “texte” par page.

## Endpoints

- `GET /health` → `{ "ok": true }`
- `POST /pdf2htmlex`

### Body JSON attendu

```json
{
  "request_id": "2025-10-06T14:58:22.526Z",
  "filename": "upload.pdf",
  "pdf_b64": "JVBERi0xLjc... (optionnel)",
  "pdf_url": "https://exemple.com/sample.pdf (optionnel, si pas de pdf_b64)",
  "options": {
    "ocr": true,
    "mode": "both",
    "injectLinks": true,
    "promoteHeadings": true,
    "graphEngine": "heuristic",
    "locale": "fr-FR",
    "returnZipB64": true
  }
}

Réponse JSON
{
  "request_id": "2025-10-06T14:58:22.526Z",
  "filename": "upload.pdf",
  "metrics": { "pages": 5 },
  "html_semantic": "<html>...<section data-page='1'><pre>...</pre></section>...</html>"
}

Lancer en local
python -m venv .venv && . .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
uvicorn app:app --reload

Déploiement Render

Start: uvicorn app:app --host 0.0.0.0 --port $PORT

Variable d’environnement : PYTHON_VERSION=3.11.9
