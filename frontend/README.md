# Nokware Frontend

Next.js 15 (App Router, TypeScript) · Tailwind CSS v4 · shadcn/ui (Radix base,
Nova preset — Lucide icons, Geist font, neutral base color, CSS variables).

## Setup

```bash
npm install
cp .env.example .env.local   # then fill in real values
npm run dev
```

The app runs at http://localhost:3000.

## Environment

Configuration is read from `frontend/.env.local` (git-ignored). See
[`.env.example`](.env.example):

- `NEXT_PUBLIC_API_URL` — base URL of the FastAPI backend (default
  `http://localhost:8000`).
- `NEXT_PUBLIC_APPWRITE_ENDPOINT` — Appwrite endpoint.
- `NEXT_PUBLIC_APPWRITE_PROJECT_ID` — Appwrite project id.

## Design tokens

The color palette and design tokens are produced by Claude Design and applied
on top of this shadcn/ui base. The Nova preset ships a neutral base color as a
starting point; the Claude Design tokens override the palette in
`src/app/globals.css`.

## Adding shadcn/ui components

```bash
npx shadcn@latest add <component>
```
