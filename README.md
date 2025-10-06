# pdf2htmlex-service

`pdf2htmlex-service` is a FastAPI microservice that wraps [`pdf2htmlEX`](https://github.com/pdf2htmlEX/pdf2htmlEX) to convert PDFs into self-contained HTML. It is designed for deployment on Render.com as a Docker web service.

## Endpoints
- `GET /health` → `{ "ok": true }`
- `POST /pdf2html`
  ```json
  {
    "request_id": "demo-1",
    "filename": "sample.pdf",
    "pdf_b64": null,
    "pdf_url": "https://example.com/sample.pdf",
    "options": {
      "embed": "all",
      "zoom": 1.0,
      "page_from": null,
      "page_to": null,
      "timeout_sec": 120,
      "returnZipB64": false
    }
  }
  ```

Responses include the conversion metrics and either the generated HTML or a base64 ZIP archive when `returnZipB64` is enabled.

## Running locally with Docker
```bash
docker build -t pdf2htmlex-service .
docker run -e PORT=10000 -p 10000:10000 pdf2htmlex-service
```
Then visit http://localhost:10000/health or http://localhost:10000/docs.

## Deploying on Render
1. Push this repository to your own GitHub/GitLab account.
2. In Render, click **New** → **Web Service**.
3. Choose **Docker** and point Render to your repository.
4. Render will detect `render.yaml` and build using the included `Dockerfile`.
5. Deploy. Render requires the application to bind to `0.0.0.0` and the port supplied in the `PORT` environment variable—this service already does that.

Render Python version is set via `PYTHON_VERSION` or `.python-version`. See the [Render documentation](https://render.com/docs/python-version) for details.

## Example `curl`
```bash
BASE="https://pdf2htmlex.onrender.com"
curl -X POST "$BASE/pdf2html" \
  -H "Content-Type: application/json" \
  -d '{"request_id":"demo-1","filename":"sample.pdf","pdf_url":"https://example.com/sample.pdf","options":{"embed":"all","returnZipB64":true}}'
```

`/health` returns `{ "ok": true }` and can be used by Render's health checks.

## Testing
```bash
pip install -r requirements.txt pytest
pytest
```

The pdf conversion test is skipped automatically if the `pdf2htmlEX` binary is not available (for example, outside the Docker image).
