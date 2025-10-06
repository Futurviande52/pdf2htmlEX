"""FastAPI microservice to convert PDFs to HTML using pdf2htmlEX."""
from __future__ import annotations

import base64
import binascii
import logging
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, Optional, Tuple

import requests
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, HttpUrl, field_validator, model_validator

logger = logging.getLogger("uvicorn.error")

DEFAULT_FILENAME = "document.pdf"
HTML_OUTPUT_NAME = "out.html"
PDF2HTMLEX_TIMEOUT = 180
PDF_DOWNLOAD_TIMEOUT = 60
PDF2HTMLEX_CMD = [
    "pdf2htmlEX",
    "--split-pages",
    "0",
    "--embed-css",
    "1",
    "--embed-image",
    "1",
    "--embed-font",
    "1",
    "--process-outline",
    "1",
    "--optimize-text",
    "1",
]


class ConversionRequest(BaseModel):
    """Incoming payload for PDF to HTML conversion."""

    request_id: Optional[str] = None
    filename: Optional[str] = None
    pdf_b64: Optional[str] = None
    pdf_url: Optional[HttpUrl] = None

    @model_validator(mode="after")
    def ensure_source_present(self) -> "ConversionRequest":
        if not self.pdf_b64 and not self.pdf_url:
            raise ValueError("One of pdf_b64 or pdf_url must be provided.")
        return self

    @field_validator("pdf_b64")
    @classmethod
    def strip_whitespace(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if isinstance(value, str) else value


class ConversionResponse(BaseModel):
    request_id: Optional[str]
    filename: str
    metrics: Dict[str, int]
    html: str


app = FastAPI(title="pdf2htmlEX microservice", version="1.0.0")


def _decode_pdf_b64(encoded: str) -> bytes:
    try:
        return base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid base64 payload provided for pdf_b64.",
        ) from exc


def _fetch_pdf_url(url: HttpUrl) -> Tuple[bytes, Optional[str]]:
    try:
        response = requests.get(str(url), timeout=PDF_DOWNLOAD_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        logger.warning("Failed to fetch PDF from URL %s: %s", url, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to download PDF from the provided URL.",
        ) from exc

    filename = Path(response.url).name or None
    return response.content, filename


def _load_pdf_bytes(payload: ConversionRequest) -> Tuple[bytes, Optional[str]]:
    if payload.pdf_b64:
        return _decode_pdf_b64(payload.pdf_b64), None
    if payload.pdf_url:
        return _fetch_pdf_url(payload.pdf_url)
    # Should be unreachable due to validator, but keeps type-checkers happy.
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="No PDF source provided.",
    )


def _truncate_message(message: str, limit: int = 4000) -> str:
    if len(message) <= limit:
        return message
    return message[: limit - 3] + "..."


def _extract_page_count(*outputs: str) -> Optional[int]:
    page_pattern = re.compile(r"pages?\s*:?\s*(\d+)", re.IGNORECASE)
    for output in outputs:
        if not output:
            continue
        match = page_pattern.search(output)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue
    return None


@app.get("/health")
def healthcheck() -> dict:
    """Simple health endpoint used by Render and other orchestrators."""
    return {"ok": True}


@app.post("/pdf2html", response_model=ConversionResponse)
def convert_pdf(payload: ConversionRequest) -> ConversionResponse:
    pdf_bytes, inferred_filename = _load_pdf_bytes(payload)
    target_filename = payload.filename or inferred_filename or DEFAULT_FILENAME

    with TemporaryDirectory(prefix="pdf2htmlx-") as tmpdir:
        tmp_path = Path(tmpdir)
        input_pdf = tmp_path / "input.pdf"
        output_html = tmp_path / HTML_OUTPUT_NAME

        input_pdf.write_bytes(pdf_bytes)

        command = [
            *PDF2HTMLEX_CMD,
            "--dest-dir",
            str(tmp_path),
            str(input_pdf),
            HTML_OUTPUT_NAME,
        ]

        logger.info("Running pdf2htmlEX for request_id=%s", payload.request_id)
        try:
            completed = subprocess.run(  # noqa: S603
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=PDF2HTMLEX_TIMEOUT,
                text=True,
            )
        except subprocess.TimeoutExpired as exc:
            logger.error(
                "pdf2htmlEX timed out after %s seconds for request_id=%s",
                PDF2HTMLEX_TIMEOUT,
                payload.request_id,
            )
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Conversion timed out.",
            ) from exc
        except subprocess.CalledProcessError as exc:
            stderr_msg = _truncate_message(exc.stderr or "Conversion failed without error output.")
            logger.error("pdf2htmlEX failed: %s", stderr_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"pdf2htmlEX failed: {stderr_msg}",
            ) from exc

        if not output_html.exists():
            logger.error("Expected HTML output not produced by pdf2htmlEX.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="pdf2htmlEX did not produce an HTML file.",
            )

        html_content = output_html.read_text(encoding="utf-8")
        html_bytes = len(html_content.encode("utf-8"))
        pages = _extract_page_count(completed.stdout, completed.stderr)

    metrics: Dict[str, int] = {"html_bytes": html_bytes}
    if pages is not None:
        metrics["pages"] = pages

    return ConversionResponse(
        request_id=payload.request_id,
        filename=target_filename,
        metrics=metrics,
        html=html_content,
    )


__all__ = ["app"]
