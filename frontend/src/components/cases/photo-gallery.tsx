"use client";

import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react";
import Image from "next/image";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

/**
 * The photos a resident sent, at a size a responder can judge. Opening them in a new tab meant leaving the case
 * to look at its evidence, and coming back to a queue that had lost the selection.
 *
 * Only ever rendered where the description is shown, so an oversight view of a personal-safety case still has no
 * photos to open.
 */
type GalleryProps = {
  photos: string[];
  testIdPrefix?: string;
  /** Whose photos these are, for the caption and the alt text: a case's are the citizen's, a petition's its own. */
  subject?: string;
};

export function PhotoGallery({ photos, testIdPrefix = "case-photo", subject = "from the citizen" }: GalleryProps) {
  const [open, setOpen] = useState<number | null>(null);
  const showing = open === null ? null : photos[open];
  useEffect(() => {
    if (open === null) return;
    const keys = (event: KeyboardEvent) => {
      if (event.key === "ArrowRight") setOpen((at) => (at === null ? at : (at + 1) % photos.length));
      if (event.key === "ArrowLeft") setOpen((at) => (at === null ? at : (at - 1 + photos.length) % photos.length));
    };
    window.addEventListener("keydown", keys);
    return () => window.removeEventListener("keydown", keys);
  }, [open, photos.length]);
  if (photos.length === 0) return null;
  const step = (by: number) => setOpen((at) => (at === null ? at : (at + by + photos.length) % photos.length));
  return (
    <>
      <ul className="grid grid-cols-3 gap-2" aria-label="Photos">
        {photos.map((url, index) => (
          <li key={url}>
            <button type="button" onClick={() => setOpen(index)} className="block w-full cursor-zoom-in rounded-md"
              aria-label={`Open photo ${index + 1} of ${photos.length}`} data-testid={`${testIdPrefix}-${index}`}>
              <Image src={url} alt={`Photo ${index + 1} ${subject}`} width={160} height={120} unoptimized
                className="aspect-4/3 w-full rounded-md border object-cover" />
            </button>
          </li>
        ))}
      </ul>
      <Dialog open={open !== null} onOpenChange={(next) => setOpen(next ? open : null)}>
        <DialogContent className="max-w-[min(94vw,1100px)] gap-3 sm:max-w-[min(94vw,1100px)]" data-testid={`${testIdPrefix}-viewer`}>
          <DialogTitle className="text-[14px] font-normal text-ink-soft">
            {open === null ? "" : `Photo ${open + 1} of ${photos.length} ${subject}`}
          </DialogTitle>
          {showing ? (
            <Image src={showing} alt={`Photo ${(open ?? 0) + 1} ${subject}`} width={1400} height={1050} unoptimized
              className="max-h-[74vh] w-full rounded-lg object-contain" />
          ) : null}
          {photos.length > 1 ? (
            <div className="flex items-center justify-between">
              <Button variant="secondary" size="sm" onClick={() => step(-1)} data-testid={`${testIdPrefix}-previous`}>
                <ChevronLeftIcon data-icon="inline-start" />
                Previous
              </Button>
              <Button variant="secondary" size="sm" onClick={() => step(1)} data-testid={`${testIdPrefix}-next`}>
                Next
                <ChevronRightIcon data-icon="inline-end" />
              </Button>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}
