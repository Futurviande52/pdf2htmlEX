#!/bin/bash
set -e

# Utiliser le port fourni par Render ou 10000 par défaut
PORT=${PORT:-10000}

echo "Starting uvicorn on port $PORT..."
exec python3 -m uvicorn app:app --host 0.0.0.0 --port "$PORT"

