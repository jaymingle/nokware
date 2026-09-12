import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

type Swatch = { name: string; hex: string; className: string };

// Temporary token showcase. Hex values are display labels copied from the spec;
// if a swatch's colour and its label disagree, the CSS token is miswired.
const SWATCHES: Swatch[] = [
  { name: "paper", hex: "#F3F5F2", className: "bg-paper" },
  { name: "paper-raised", hex: "#FFFFFF", className: "bg-paper-raised" },
  { name: "paper-warm", hex: "#FDFAF3", className: "bg-paper-warm" },
  { name: "paper-subtle", hex: "#FAFBF9", className: "bg-paper-subtle" },
  { name: "ink", hex: "#17242B", className: "bg-ink" },
  { name: "ink-soft", hex: "#4A5A5F", className: "bg-ink-soft" },
  { name: "ink-muted", hex: "#8D9A9E", className: "bg-ink-muted" },
  { name: "hairline", hex: "#D6DAD4", className: "bg-hairline" },
  { name: "teal", hex: "#1F6F5C", className: "bg-teal" },
  { name: "teal-tint", hex: "#E7F0EC", className: "bg-teal-tint" },
  { name: "gold", hex: "#A9761F", className: "bg-gold" },
  { name: "gold-tint", hex: "#F4ECDA", className: "bg-gold-tint" },
  { name: "brick", hex: "#8C3230", className: "bg-brick" },
  { name: "brick-tint", hex: "#F5E9E7", className: "bg-brick-tint" },
];

const TEXT_COLORS = [
  { name: "text-ink", className: "text-ink" },
  { name: "text-ink-soft", className: "text-ink-soft" },
  { name: "text-ink-muted", className: "text-ink-muted" },
  { name: "text-teal", className: "text-teal" },
  { name: "text-gold", className: "text-gold" },
  { name: "text-brick", className: "text-brick" },
];

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-2xl">{title}</h2>
      {children}
    </section>
  );
}

function ColorSwatches() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
      {SWATCHES.map((swatch) => (
        <div key={swatch.name} className="flex flex-col gap-1.5">
          <div className={`h-16 rounded-lg border border-hairline ${swatch.className}`} />
          <span className="text-sm font-medium">{swatch.name}</span>
          <span className="text-xs text-ink-soft">{swatch.hex}</span>
        </div>
      ))}
    </div>
  );
}

function TextColors() {
  return (
    <div className="flex flex-wrap gap-x-6 gap-y-2 text-base font-medium">
      {TEXT_COLORS.map((color) => (
        <span key={color.name} className={color.className}>
          {color.name}
        </span>
      ))}
    </div>
  );
}

function Typography() {
  return (
    <div className="grid gap-8 sm:grid-cols-2">
      <div className="flex flex-col gap-3">
        <p className="text-xs text-ink-soft">Fraunces 500 · display / headings</p>
        <p className="font-heading text-5xl font-medium">Ledger 48</p>
        <p className="font-heading text-3xl font-medium">Budget reports 30</p>
        <p className="font-heading text-xl font-medium">Case history 20</p>
        <p className="font-heading text-base font-medium">Ward notice 16</p>
      </div>
      <div className="flex flex-col gap-3">
        <p className="text-xs text-ink-soft">Public Sans · body / UI</p>
        <p className="text-base">Regular 400 · 16px — The assembly publishes every approved budget.</p>
        <p className="text-base font-medium">Medium 500 · 16px — Report a broken streetlight.</p>
        <p className="text-sm text-ink-soft">Regular 400 · 14px — Secondary text in ink-soft.</p>
        <p className="text-xs text-ink-soft">Regular 400 · 12px — Captions stay in ink-soft.</p>
      </div>
    </div>
  );
}

function SampleCard() {
  return (
    <Card className="max-w-md">
      <CardHeader>
        <CardTitle>2026 Mid-Year Budget Review</CardTitle>
        <CardDescription>Finance department · published 12 Aug 2026</CardDescription>
      </CardHeader>
      <CardContent>
        12px radius, 0.5px hairline border, paper-raised surface, no shadow.
      </CardContent>
      <CardFooter className="text-xs text-ink-soft">Card footer on muted</CardFooter>
    </Card>
  );
}

function Buttons() {
  return (
    <div className="flex flex-wrap gap-3">
      <Button data-testid="showcase-button-primary">Primary</Button>
      <Button variant="secondary" data-testid="showcase-button-secondary">
        Secondary
      </Button>
      <Button variant="destructive" data-testid="showcase-button-destructive">
        Destructive
      </Button>
    </div>
  );
}

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-12 px-6 py-12">
      <header className="flex flex-col gap-2">
        <h1 className="text-4xl">Nokware design system</h1>
        <p className="text-ink-soft">Token showcase · light surfaces only</p>
      </header>
      <Section title="Colours">
        <ColorSwatches />
        <TextColors />
      </Section>
      <Section title="Typography">
        <Typography />
      </Section>
      <Section title="Card">
        <SampleCard />
      </Section>
      <Section title="Buttons">
        <Buttons />
      </Section>
    </main>
  );
}
