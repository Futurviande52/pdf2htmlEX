# pdf2htmlx-service

Micro-service FastAPI prêt pour la production convertissant des documents PDF en HTML fidèle grâce à [pdf2htmlEX](https://github.com/coolwanglu/pdf2htmlEX). Le service enveloppe l'outil en ligne de commande avec des paramètres optimisés pour l'intégration web (`--split-pages 0 --embed-css 1 --embed-image 1 --embed-font 1 --process-outline 1 --optimize-text 1`).

## Fonctionnalités

- API REST avec FastAPI (Uvicorn) exposant :
  - `GET /health` : vérification de l'état.
  - `POST /pdf2html` : conversion via PDF encodé en base64 ou accessible par URL HTTP/HTTPS.
- Gestion des erreurs explicites (400 en cas de payload invalide, 504 en cas de dépassement de temps).
- Nettoyage automatique des fichiers temporaires.
- Image Docker légère basée sur `bwits/pdf2htmlex:alpine` avec Python 3.11.

## Prérequis

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) pour un usage local **ou**
- Un compte [Render](https://render.com/) pour le déploiement managé.

## Lancement local (Docker)

```bash
docker build -t pdf2htmlx ./pdf2htmlx-service

docker run --rm -p 8080:8080 pdf2htmlx
```

Tester rapidement la conversion (nécessite `curl` et `jq`) :

```bash
curl -X POST http://localhost:8080/pdf2html \
     -H "Content-Type: application/json" \
     -d '{"pdf_url":"https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf","request_id":"demo-1"}' \
     | jq -r .html > out.html
```

Ouvrez ensuite `out.html` dans votre navigateur pour vérifier le rendu.

## Déploiement sur Render

1. Poussez ce répertoire dans un dépôt Git public ou privé.
2. Connectez votre dépôt à Render et créez un nouveau service **Web**.
3. Render détecte automatiquement le `Dockerfile` à la racine du répertoire (dans `pdf2htmlx-service/`).
4. Aucun réglage de port n'est nécessaire : le process écoute `0.0.0.0:${PORT:-8080}` comme requis par Render.

Le fichier [`render.yaml`](render.yaml) fournit un blueprint minimal pour l'Infrastructure as Code Render.

## API

### Requête

`POST /pdf2html`

```json
{
  "request_id": "demo-1",
  "filename": "rapport.pdf",
  "pdf_b64": "...",
  "pdf_url": "https://exemple.com/doc.pdf"
}
```

- `pdf_b64` **ou** `pdf_url` est requis. Si les deux sont fournis, `pdf_b64` est prioritaire.
- `filename` est facultatif et utilisé uniquement dans la réponse pour référence.

### Réponse

```json
{
  "request_id": "demo-1",
  "filename": "rapport.pdf",
  "metrics": {
    "pages": 3,
    "html_bytes": 128764
  },
  "html": "<!DOCTYPE html>..."
}
```

### Codes d'état principaux

- `200 OK` : conversion réussie.
- `400 Bad Request` : base64 invalide ou URL inaccessible.
- `504 Gateway Timeout` : conversion dépassant 180 secondes.
- `500 Internal Server Error` : échec `pdf2htmlEX` ou sortie manquante.

## Notes supplémentaires

- Les sorties HTML peuvent être volumineuses ; activez la compression HTTP côté reverse proxy/plateforme si nécessaire.
- Les indicateurs `pdf2htmlEX` sont documentés dans la [documentation officielle](https://github.com/coolwanglu/pdf2htmlEX/wiki/pdf2htmlEX-Command-Line-Options).
- Les logs applicatifs utilisent le logger `uvicorn.error` pour s'aligner sur la stack Uvicorn.

## Fichiers fournis

- `app.py` : application FastAPI.
- `requirements.txt` : dépendances Python.
- `Dockerfile` : build de l'image Docker.
- `render.yaml` : blueprint Render.
- `README.md` : ce guide.
