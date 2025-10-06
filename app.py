import base64
import binascii
import io
import logging
import os
import shutil
import subprocess
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from typing import Literal, Optional

import requests
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, root_validator
from pypdf import PdfReader

logger = logging.getLogger("uvicorn.error")

MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB
PDF_DOWNLOAD_TIMEOUT = 60


class PdfOptions(BaseModel):
    embed: Literal["all", "none", "css", "image", "font"] = "all"
    zoom: float = Field(1.0, gt=0)
    page_from: Optional[int] = Field(default=None, ge=1)
    page_to: Optional[int] = Field(default=None, ge=1)
    timeout_sec: int = Field(120, ge=1, le=900)
    returnZipB64: bool = False

    @root_validator
    def validate_page_range(cls, values):
        start = values.get("page_from")
        end = values.get("page_to")
        if start and end and start > end:
            raise ValueError("page_from must be <= page_to")
        return values


class Pdf2HtmlIn(BaseModel):
    request_id: Optional[str] = None
    filename: Optional[str] = None
    pdf_b64: Optional[str] = None
    pdf_url: Optional[str] = None
    options: PdfOptions = Field(default_factory=PdfOptions)

    @root_validator
    def validate_source(cls, values):
        pdf_b64 = values.get("pdf_b64")
        pdf_url = values.get("pdf_url")
        if not pdf_b64 and not pdf_url:
            raise ValueError("At least one of pdf_b64 or pdf_url must be provided")
        return values

app = FastAPI(title="pdf2htmlex-service")


def _decode_pdf_from_b64(data: str) -> bytes:
    try:
        return base64.b64decode(data, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid base64 payload: {exc}")
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid base64 payload: {exc}")


def _download_pdf(url: str) -> bytes:
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="pdf_url must start with http:// or https://")
    try:
        response = requests.get(url, timeout=PDF_DOWNLOAD_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to download PDF: {exc}")
    return response.content


def _write_pdf_to_disk(pdf_bytes: bytes, destination: Path) -> None:
    destination.write_bytes(pdf_bytes)


def _build_command(options: PdfOptions, input_pdf: Path, output_html: Path) -> list[str]:
    embed_map = {
        "all": {"css": "1", "image": "1", "font": "1"},
        "none": {"css": "0", "image": "0", "font": "0"},
        "css": {"css": "1", "image": "0", "font": "0"},
        "image": {"css": "0", "image": "1", "font": "0"},
        "font": {"css": "0", "image": "0", "font": "1"},
    }
    embed_flags = embed_map[options.embed]

    command = [
        "pdf2htmlEX",
        "--embed-css",
        embed_flags["css"],
        "--embed-image",
        embed_flags["image"],
        "--embed-font",
        embed_flags["font"],
        "--zoom",
        str(options.zoom),
    ]

    if options.page_from is not None:
        command.extend(["--first-page", str(options.page_from)])
    if options.page_to is not None:
        command.extend(["--last-page", str(options.page_to)])

    command.extend([str(input_pdf), str(output_html)])
    return command


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    body = (await request.body()).decode("utf-8", errors="ignore")
    logger.error("422 validation error request_body=%s errors=%s", body[:1000], exc.errors())
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": exc.errors()})


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/pdf2html")
def pdf2html(payload: Pdf2HtmlIn):
    request_id = payload.request_id or str(uuid.uuid4())
    start_ts = time.perf_counter()

    if payload.pdf_b64:
        pdf_bytes = _decode_pdf_from_b64(payload.pdf_b64)
        source = "b64"
    else:
        assert payload.pdf_url  # for type checker
        pdf_url = payload.pdf_url.strip()
        if not pdf_url:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="pdf_url must be non-empty")
        pdf_bytes = _download_pdf(pdf_url)
        source = "url"

    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="PDF exceeds 20MB limit")

    try:
        pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
        page_count = len(pdf_reader.pages)
    except Exception:
        page_count = 0

    tmp_dir = Path(tempfile.mkdtemp(prefix="pdf2htmlex_"))
    pdf_path = tmp_dir / "input.pdf"
    html_path = tmp_dir / "output.html"

    try:
        _write_pdf_to_disk(pdf_bytes, pdf_path)
        command = _build_command(payload.options, pdf_path, html_path)

        try:
            process = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=payload.options.timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="pdf2htmlEX timed out")

        if process.returncode != 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "message": "pdf2htmlEX failed",
                    "exit_code": process.returncode,
                    "stderr": process.stderr,
                },
            )

        if not html_path.exists():
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="HTML output not produced")

        if payload.options.returnZipB64:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for path in tmp_dir.rglob("*"):
                    if path.is_file() and path != pdf_path:
                        zf.write(path, arcname=path.relative_to(tmp_dir))
            html_output_bytes = zip_buffer.getvalue()
            response_payload = {
                "html_zip_b64": base64.b64encode(html_output_bytes).decode("utf-8"),
            }
            return_size = len(html_output_bytes)
        else:
            html_output_bytes = html_path.read_bytes()
            response_payload = {"html": html_output_bytes.decode("utf-8", errors="ignore")}
            return_size = len(html_output_bytes)

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    elapsed_ms = int((time.perf_counter() - start_ts) * 1000)

    logger.info(
        "request_id=%s source=%s bytes_in=%s pages=%s elapsed_ms=%s bytes_out=%s",
        request_id,
        source,
        len(pdf_bytes),
        page_count,
        elapsed_ms,
        return_size,
    )

    response = {
        "request_id": request_id,
        "metrics": {"pages": page_count, "elapsed_ms": elapsed_ms},
    }
    response.update(response_payload)
    return response


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "10000")), reload=False)
