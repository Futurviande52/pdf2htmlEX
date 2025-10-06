from __future__ import annotations

import base64
import html
import logging
from io import BytesIO
from typing import Literal, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl, field_validator, model_validator
from pypdf import PdfReader

log = logging.getLogger("uvicorn.error")

app = FastAPI(title="pdf2htmlEX (light)")

# CORS (ouvrir/resserrer selon besoin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PdfOptions(BaseModel):
    # Options conservées pour compatibilité n8n, certaines non utilisées ici
    ocr: bool = True
    mode: Literal["text", "both"] = "both"
    injectLinks: bool = True
    promoteHeadings: bool = True
    graphEngine: Literal["heuristic", "none"] = "heuristic"
    locale: str = "fr-FR"
    returnZipB64: bool = True

    @field_validator("locale")
    @classmethod
    def _normalize_locale(cls, v: str) -> str:
        return v or "fr-FR"

    @model_validator(mode="after")
    def _coherence(self) -> "PdfOptions":
        if self.mode not in {"text", "both"}:
            raise ValueError("mode must be 'text' or 'both'")
        return self


class Pdf2HtmlIn(BaseModel):
    request_id: Optional[str] = None
    filename: Optional[str] = None
    pdf_b64: Optional[str] = None
    pdf_url: Optional[HttpUrl] = None
    options: Optional[PdfOptions] = PdfOptions()

    @model_validator(mode="after")
    def _one_source(self) -> "Pdf2HtmlIn":
        if not self.pdf_b64 and not self.pdf_url:
            raise ValueError("Provide either pdf_b64 or pdf_url")
        return self


class Pdf2HtmlOut(BaseModel):
    request_id: Optional[str] = None
    filename: Optional[str] = None
    html_semantic: str
    metrics: dict


@app.get("/health")
def health() -> dict:
    return {"ok": True}


def _load_pdf_bytes(payload: Pdf2HtmlIn) -> bytes:
    if payload.pdf_b64:
        try:
            return base64.b64decode(payload.pdf_b64, validate=True)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Invalid base64: {e}")
    assert payload.pdf_url is not None
    try:
        with httpx.Client(timeout=httpx.Timeout(30.0)) as client:
            r = client.get(str(payload.pdf_url))
            r.raise_for_status()
            return r.content
    except httpx.HTTPError as e:
        log.exception("Failed to download pdf from %s", payload.pdf_url)
        raise HTTPException(status_code=400, detail=f"Failed to download pdf_url: {e}")


def _pdf_to_html(blob: bytes, opts: PdfOptions) -> tuple[str, int]:
    """Extraction texte par page et encapsulation simple en HTML."""
    reader = PdfReader(BytesIO(blob))
    html_parts = [
        "<html><head><meta charset='utf-8'>"
        "<style>pre{white-space:pre-wrap;word-break:break-word}</style>"
        "</head><body>"
    ]
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            log.exception("extract_text failed on page %s", i)
            text = ""
        html_parts.append(f"<section data-page='{i}'><pre>{html.escape(text)}</pre></section>")
    html_parts.append("</body></html>")
    html_doc = "\n".join(html_parts)
    return html_doc, len(reader.pages)


@app.post("/pdf2htmlex", response_model=Pdf2HtmlOut)
def pdf2htmlex(payload: Pdf2HtmlIn) -> Pdf2HtmlOut:
    blob = _load_pdf_bytes(payload)
    html_doc, pages = _pdf_to_html(blob, payload.options or PdfOptions())
    return Pdf2HtmlOut(
        request_id=payload.request_id,
        filename=payload.filename or "upload.pdf",
        html_semantic=html_doc,
        metrics={"pages": pages},
    )


# Optionnel: racine
@app.get("/")
def root() -> dict:
    return {"service": "pdf2htmlEX (light)", "endpoints": ["/health", "/pdf2htmlex"]}

