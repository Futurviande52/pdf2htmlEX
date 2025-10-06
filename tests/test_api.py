import shutil

import pytest
from fastapi.testclient import TestClient

from app import app

client = TestClient(app)

SAMPLE_PDF_B64 = (
    "JVBERi0xLjQKJeLjz9MKMSAwIG9iago8PAovVHlwZSAvQ2F0YWxvZwovUGFnZXMgMiAwIFIKPj4K"
    "ZW5kb2JqCjIgMCBvYmoKPDwKL1R5cGUgL1BhZ2VzCi9LaWRzIFszIDAgUl0KL0NvdW50IDEKPj4K"
    "ZW5kb2JqCjMgMCBvYmoKPDwKL1R5cGUgL1BhZ2UKL1BhcmVudCAyIDAgUgovTWVkaWFCb3ggWzAg"
    "MCA2MTIgNzkyXQovQ29udGVudHMgNCAwIFIKPj4KZW5kb2JqCjQgMCBvYmoKPDwKL0xlbmd0aCAx"
    "MSA+PgpzdHJlYW0KQlQKL0YgMTIgVGYKMTAwIDcwMCBUZAooSGVsbG8pIFRqCkVUCmVuZHN0cmVh"
    "bQplbmRvYmoKeHJlZgowIDYKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAwMDEwIDAwMDAwIG4g"
    "CjAwMDAwMDAwNzAgMDAwMDAgbiAKMDAwMDAwMDE1NCAwMDAwMCBuIAowMDAwMDAwMjM3IDAwMDAw"
    "IG4gCnRyYWlsZXIKPDwKL1NpemUgNgovUm9vdCAxIDAgUgovSW5mbyA1IDAgUgo+PgpzdGFydHhy"
    "ZWYKMjk4CiUlRU9G"
)


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.skipif(shutil.which("pdf2htmlEX") is None, reason="pdf2htmlEX not installed")
def test_pdf2html_b64_success():
    response = client.post(
        "/pdf2html",
        json={
            "request_id": "test",
            "filename": "hello.pdf",
            "pdf_b64": SAMPLE_PDF_B64,
            "options": {"returnZipB64": False},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["request_id"] == "test"
    assert data["metrics"]["pages"] >= 1
    assert "html" in data
    assert data["html"].lower().startswith("<!doctype")


def test_validation_error_when_missing_sources():
    response = client.post("/pdf2html", json={})
    assert response.status_code == 422
    assert response.json()["detail"]
