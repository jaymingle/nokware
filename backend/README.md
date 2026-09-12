# Nokware Backend

Python 3.11 · FastAPI · LangChain · Google Gemini (`gemini-2.0-flash`,
`text-embedding-004`) · Appwrite SDK · MinIO · Postgres/pgvector.

## Install

With [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Or with pip in a virtualenv:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Environment

Copy the example file and fill in real values (pull secrets from Vaultwarden —
do **not** commit `.env`):

```bash
cp .env.example .env
```

Required vars: `APPWRITE_ENDPOINT`, `APPWRITE_PROJECT_ID`, `APPWRITE_API_KEY`,
`POSTGRES_URL`, `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`,
`MINIO_LEDGER_BUCKET`, `MINIO_PHOTOS_BUCKET`, `GEMINI_API_KEY`.

## Run

```bash
uvicorn app.main:app --reload
```

Health check: `GET http://localhost:8000/health` → `{"status": "ok"}`.
