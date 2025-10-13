from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import base64
import requests
import tempfile
import os
import shutil
import subprocess
from typing import Optional

# Créer l'application FastAPI
app = FastAPI(
    title="PDF to HTML Conversion Service",
    description="Service de conversion PDF vers HTML utilisant pdf2htmlEX",
    version="1.0.0"
)

# ==================== ENDPOINT RACINE ====================

@app.get("/")
async def root():
    """Endpoint racine pour vérifier que le service est en ligne"""
    return {
        "status": "online",
        "service": "PDF to HTML Conversion Service",
        "version": "1.0.0",
        "endpoints": {
            "/": "Status check",
            "/health": "Health check",
            "/convert": "Convert PDF to HTML (POST)"
        }
    }

@app.get("/health")
async def health():
    """Health check endpoint pour Render"""
    return {"status": "healthy"}

# ==================== ENDPOINT /convert POUR N8N ====================
# Compatible avec le workflow n8n qui attend { "html_content": "..." }

@app.post("/convert")
async def convert_pdf_to_html_n8n(request: Request):
    """
    Endpoint compatible avec n8n
    Convertit un PDF en HTML fidèle en utilisant pdf2htmlEX
    
    Body attendu:
    {
        "pdf_b64": "...",  // optionnel - PDF encodé en base64
        "pdf_url": "...",  // optionnel - URL du PDF
        "file_name": "..." // optionnel - nom du fichier
    }
    
    Réponse:
    {
        "success": true,
        "html_content": "...",
        "file_name": "...",
        "size": 12345
    }
    """
    try:
        data = await request.json()
        
        # Récupérer le PDF
        pdf_content = None
        file_name = data.get('file_name', 'input.pdf')
        
        if data.get('pdf_b64'):
            # Décoder le base64
            try:
                pdf_content = base64.b64decode(data['pdf_b64'])
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid base64: {e}")
        
        elif data.get('pdf_url'):
            # Télécharger depuis l'URL
            try:
                response = requests.get(data['pdf_url'], timeout=60)
                response.raise_for_status()
                pdf_content = response.content
                # Extraire le nom du fichier de l'URL
                if not file_name or file_name == "input.pdf":
                    file_name = data['pdf_url'].split('/')[-1]
                    if not file_name.endswith('.pdf'):
                        file_name = 'input.pdf'
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to download PDF: {e}")
        
        else:
            raise HTTPException(status_code=400, detail="Either pdf_b64 or pdf_url must be provided")
        
        # Créer un fichier temporaire pour le PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_pdf:
            tmp_pdf.write(pdf_content)
            pdf_path = tmp_pdf.name
        
        # Créer un répertoire temporaire pour la sortie
        output_dir = tempfile.mkdtemp()
        output_html = os.path.join(output_dir, 'output.html')
        
        try:
            # Exécuter pdf2htmlEX
            subprocess.run([
                'pdf2htmlEX',
                '--zoom', '1.3',
                '--process-outline', '0',
                '--embed-css', '1',
                '--embed-javascript', '1',
                '--embed-image', '1',
                '--embed-font', '1',
                pdf_path,
                'output.html'
            ], cwd=output_dir, check=True, capture_output=True, timeout=300)
            
            # Lire le HTML généré
            if not os.path.exists(output_html):
                raise HTTPException(status_code=500, detail="HTML output file not created")
            
            with open(output_html, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Préparer le nom du fichier de sortie
            output_filename = file_name.replace('.pdf', '.html')
            
            return {
                "success": True,
                "html_content": html_content,
                "file_name": output_filename,
                "size": len(html_content)
            }
        
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode('utf-8') if e.stderr else str(e)
            raise HTTPException(status_code=500, detail=f"pdf2htmlEX failed: {error_msg}")
        
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="Conversion timeout (>5 minutes)")
        
        finally:
            # Nettoyer les fichiers temporaires
            try:
                os.unlink(pdf_path)
            except:
                pass
            try:
                shutil.rmtree(output_dir)
            except:
                pass
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

# ==================== DÉMARRAGE ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

