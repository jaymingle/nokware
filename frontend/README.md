# Nokware Frontend

Next.js 16 (App Router, TypeScript) · Tailwind CSS v4 · shadcn/ui (Radix base,
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

## Accessibility

The target is WCAG 2.1 AA, with WCAG 2.5.5's 44px touch target taken on as
well: most people here reach Nokware on a phone, and the page carrying the
emergency numbers is the one where a mis-tap costs most.

What the code holds to:

- **Colour is never the only signal.** Every inline link is underlined, not
  underlined on hover, and every text token clears 4.5:1 on every surface it is
  used on (see the palette comments in `src/app/globals.css`).
- **Every chart has its numbers in text.** The SVG is `aria-hidden` and the same
  figures are in a visually hidden table beside it, with a suppressed count read
  as "fewer than 5" rather than left blank — the same rule the visible chart
  follows.
- **A control is at least 44px on a touch screen.** One rule in the base layer,
  scoped to `pointer: coarse`; anything that is a control but reads as a link
  carries `data-touch-target`. A link inside a sentence is exempt, as WCAG
  exempts it.
- **Focus goes where the person asked it to.** A skip link is the first thing
  focus reaches on every page, and when one step replaces another — the report
  form replacing the safety question — the new step takes the focus with it
  (`src/hooks/use-step-focus.ts`).
- **Heading levels never skip**, so the outline a screen reader lists matches
  the page. A panel used at more than one depth takes its level as a prop
  instead of assuming one.

The audit was axe-core over every public page and every signed-in portal page as
each of the three roles, in each page's first state and in the states only
reaching for something reveals — the chat panel open, both report forms, an
answered question with its chart and sources — plus the whole of filing a report
with nothing but a keyboard. Touch targets were measured on a 390px screen.
Sign-in for the portal pass used a server-minted token
(`backend/scripts/mint_portal_token.py`), so no password went near the browser.

Two limitations stand, and neither is closed by the automated pass:

- **No screen-reader testing with a real user.** Automated rules catch some of
  what matters and none of whether the page makes sense read aloud. Nothing here
  should be read as claiming otherwise.
- **The photos field on the report form is two tab stops for one action** — the
  hidden file input, which is labelled and works, and the "Add photos" button
  beside it. Untidy rather than broken.
