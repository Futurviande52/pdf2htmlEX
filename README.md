# pdf2htmlEX (FastAPI + PyMuPDF)

Service minimal qui convertit un PDF en HTML texte (extraction “text”) via FastAPI.

## Endpoints
- `GET /health` → `{ "ok": true }`
- `POST /pdf2html` (alias `/pdf2htmlex`)
  ```json
  {
    "request_id": "demo-1",
    "filename": "upload.pdf",
    "pdf_b64": "<BASE64 PDF>",
    "pdf_url": null
  }


ou

{ "request_id": "demo-2", "pdf_url": "https://example.com/sample.pdf" }

Local
python -m venv .venv && . .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r pdf2htmlex-service/requirements.txt
uvicorn pdf2htmlex-service.app:app --reload


Visiter http://127.0.0.1:8000/docs.

Render

Ce repo inclut render.yaml et runtime.txt. Sur Render:

New → Web Service → “Use existing repo”

Laisse Render détecter render.yaml

Déploie. L’URL ressemble à https://pdf2htmlex-xxxxx.onrender.com

cURL test
curl -s -X GET "https://<host>/health"
curl -s -X POST "https://<host>/pdf2html" \
  -H "Content-Type: application/json" \
  -d '{"request_id":"demo-2","pdf_url":"https://example.com/sample.pdf"}' | head

n8n (HTTP Request node)

Method: POST

URL: https://<host>/pdf2html

Headers: Content-Type: application/json, Accept: application/json

Body (JSON):

{
  "request_id": "{{$json.request_id || new Date().toISOString()}}",
  "filename": "{{$json.filename || 'upload.pdf'}}",
  "pdf_b64": "{{$json.pdf_b64}}",
  "pdf_url": null
}
