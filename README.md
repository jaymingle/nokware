# Nokware

Nokware is a civic-transparency platform for a Ghanaian municipal assembly. It
pairs a public **Ledger** — searchable department documents answered by a
Retrieval-Augmented Generation (RAG) assistant that cites its sources — with a
**citizen reporting** system for civic-service, public-safety, and
personal-safety cases routed to the responsible department. Data lives across
Appwrite (auth, teams, document metadata, reports, case history), a
Postgres/pgvector store (RAG chunks and embeddings), and MinIO (document and
photo files).

This repository is a monorepo with two applications:

- [`backend/`](backend/README.md) — Python 3.11 · FastAPI · LangChain · Gemini ·
  Appwrite SDK · MinIO · pgvector.
- [`frontend/`](frontend/README.md) — Next.js 16 (App Router, TypeScript,
  Tailwind) with shadcn/ui.
