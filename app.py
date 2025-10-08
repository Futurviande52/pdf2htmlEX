from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, HttpUrl
from starlette.middleware.gzip import GZipMiddleware  # <-- NEW
import base64, requests, html as html_mod
import fitz  # PyMuPDF
import logging

logger = logging.getLogger("uvicorn.error")

app = FastAPI()
app.add_middleware(GZipMiddleware, minimum_size=1024)  # <-- compress les grosses réponses

class Pdf2HtmlIn(BaseModel):
    request_id: str | None = None
    filename: str | None = None
    pdf_b64: str | None = None
    pdf_url: HttpUrl | None = None
    # ---- options pour réduire la taille / limiter les pages ----
    page_from: int | None = None         # 1-based, inclusif
    page_to: int | None = None           # 1-based, inclusif
    with_colors: bool = True
    with_font_style: bool = True         # gras/italique
    with_font_size: bool = False         # par défaut off (évite d’ajouter des tailles partout)
    use_css_classes: bool = True         # factorise les styles (très fort pour réduire la taille)

@app.get("/health")
def health():
    return {"ok": True}

def _load_pdf_bytes(body: Pdf2HtmlIn) -> bytes:
    if body.pdf_b64:
        try:
            return base64.b64decode(body.pdf_b64, validate=True)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid base64: {e}")
    if body.pdf_url:
        r = requests.get(str(body.pdf_url), timeout=60)
        r.raise_for_status()
        return r.content
    raise HTTPException(status_code=400, detail="Provide pdf_b64 or pdf_url")

# ------------------ utilitaires style ------------------

def _rgb_to_hex(c):
    # accepte int 0xRRGGBB ou tuple/list (r,g,b) en 0..1 ou 0..255
    if isinstance(c, int):
        return f"#{c:06x}"
    if isinstance(c, (list, tuple)) and len(c) >= 3:
        r, g, b = c[:3]
        if isinstance(r, float) and r <= 1.0:
            r, g, b = int(r*255), int(g*255), int(b*255)
        else:
            r, g, b = int(r), int(g), int(b)
        return f"#{r:02x}{g:02x}{b:02x}"
    return None

def _canonical_style_str(hexcol, bold, italic, size_px, opts: Pdf2HtmlIn) -> str | None:
    """Construit une chaîne de style canonique (ordre stable) selon les options."""
    parts = []
    if opts.with_colors and hexcol and hexcol.lower() != "#000000":
        parts.append(f"color:{hexcol}")
    if opts.with_font_style and bold:
        parts.append("font-weight:bold")
    if opts.with_font_style and italic:
        parts.append("font-style:italic")
    if opts.with_font_size and size_px:
        parts.append(f"font-size:{int(round(size_px))}px")
    return ";".join(parts) if parts else None

def _page_to_semantic_html(page: fitz.Page, opts: Pdf2HtmlIn,
                           style_map: dict, css_rules: dict) -> str:
    """Construit un HTML sémantique léger pour 1 page et remplit style_map/css_rules si use_css_classes."""
    data = page.get_text("dict")
    out = []
    out.append("<article>")
    for block in data.get("blocks", []):
        if block.get("type") != 0:  # texte uniquement
            continue
        out.append("<p>")
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                raw = span.get("text", "")
                if not raw:
                    continue
                txt = html_mod.escape(raw)

                # détection styles
                hexcol = _rgb_to_hex(span.get("color"))
                font_name = (span.get("font") or "").lower()
                bold = "bold" in font_name
                italic = ("italic" in font_name) or ("oblique" in font_name)
                size = span.get("size")  # float

                style_str = _canonical_style_str(hexcol, bold, italic, size, opts)

                if style_str:
                    if opts.use_css_classes:
                        # factorisation via classes CSS
                        cls = style_map.get(style_str)
                        if cls is None:
                            cls = f"s{len(style_map)}"
                            style_map[style_str] = cls
                            css_rules[cls] = style_str
                        txt = f'<span class="{cls}">{txt}</span>'
                    else:
                        txt = f'<span style="{style_str}">{txt}</span>'

                out.append(txt)
            out.append("<br/>")
        out.append("</p>")
    out.append("</article>")
    return "".join(out)

@app.post("/pdf2html")
def pdf2html(payload: Pdf2HtmlIn):
    blob = _load_pdf_bytes(payload)
    doc = fitz.open(stream=blob, filetype="pdf")

    # borne pages
    p0 = (payload.page_from - 1) if payload.page_from and payload.page_from > 0 else 0
    p1 = payload.page_to if payload.page_to and payload.page_to > 0 else doc.page_count
    p0 = max(0, min(p0, doc.page_count))
    p1 = max(p0+1, min(p1, doc.page_count))

    # factorisation CSS
    style_map: dict[str, str] = {}   # style_str -> cls
    css_rules: dict[str, str] = {}   # cls -> style_str

    body_parts = []
    pages = 0
    for i in range(p0, p1):
        page = doc.load_page(i)
        pages += 1
        body_parts.append(f"<section data-page='{i+1}'>")
        body_parts.append(_page_to_semantic_html(page, payload, style_map, css_rules))
        body_parts.append("</section>")
    doc.close()

    # CSS global en tête, facteur important de réduction de taille
    css_head = []
    if payload.use_css_classes and css_rules:
        css_head.append("<style>")
        for cls, rule in css_rules.items():
            css_head.append(f".{cls}{{{rule}}}")
        css_head.append("</style>")

    html_full = "".join([
        "<html><head><meta charset='utf-8'>",
        *css_head,
        "</head><body>",
        *body_parts,
        "</body></html>",
    ])

    return {
        "request_id": payload.request_id,
        "html_semantic": html_full,
        "metrics": {
            "pages": pages,
            "styles": len(css_rules),
            "use_css_classes": payload.use_css_classes,
            "with_colors": payload.with_colors,
            "with_font_style": payload.with_font_style,
            "with_font_size": payload.with_font_size,
            "page_range": [p0+1, p1],
        },
    }

# Handler 422 (inchangé)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    body = (await request.body()).decode("utf-8", errors="ignore")
    logger.error("422 payload=%s errors=%s", body[:1000], exc.errors())
    return JSONResponse(status_code=422, content={"detail": exc.errors()})
