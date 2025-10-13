FROM pdf2htmlex/pdf2htmlex:0.18.8.rc2-master-20200820-ubuntu-20.04-x86_64

RUN apt-get update \
 && apt-get install -y python3 python3-pip curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY app.py .
COPY start.sh .

# Normaliser les fins de ligne CRLF -> LF et rendre exécutable
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh

ENV PORT=10000
ENV PYTHONUNBUFFERED=1

EXPOSE 10000

# Healthcheck interne pour que le proxy sache si l'app est UP
HEALTHCHECK --interval=20s --timeout=5s --start-period=20s --retries=5 \
  CMD curl -fsS http://127.0.0.1:${PORT:-10000}/health || exit 1

CMD ["./start.sh"]

