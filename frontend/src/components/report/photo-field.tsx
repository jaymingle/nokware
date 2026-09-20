"use client";

import { ImagePlusIcon, XIcon } from "lucide-react";
import Image from "next/image";
import { useEffect, useRef, useState, type ChangeEvent } from "react";

import { ErrorNote } from "@/components/documents/panels";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { PHOTO_TYPES, addPhotos, type PhotoLimits, type ReportPhoto } from "@/lib/report/photos";
import { shrink } from "@/lib/report/shrink";
import { limitLabel } from "@/lib/uploads";

function Thumb({ photo, index, onRemove, testId }: { photo: ReportPhoto; index: number; onRemove: () => void; testId: string }) {
  return (
    <li className="relative">
      <Image src={photo.url} alt={`Photo ${index + 1}`} width={160} height={120} unoptimized className="aspect-4/3 w-full rounded-md border object-cover" />
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove photo ${index + 1}`}
        className="absolute top-1 right-1 grid size-7 place-items-center rounded-md bg-ink/80 text-paper hover:bg-ink"
        data-testid={`${testId}-remove-${index}`}
      >
        <XIcon className="size-4" />
      </button>
    </li>
  );
}

function useRevokeOnUnmount(photos: ReportPhoto[]) {
  const latest = useRef(photos);
  useEffect(() => {
    latest.current = photos;
  }, [photos]);
  useEffect(() => () => latest.current.forEach((photo) => URL.revokeObjectURL(photo.url)), []);
}

type PhotoFieldProps = {
  photos: ReportPhoto[];
  onChange: (photos: ReportPhoto[]) => void;
  limits: PhotoLimits;
  hint: string;
  /** What this field belongs to, which names its input and its test ids: "report", "petition". */
  name?: string;
  label?: string;
};

/**
 * Choosing photos, shrinking them in the browser and showing what was chosen. One field, wherever Nokware takes a
 * photo: a report, an escalation, a petition. What differs between them is the limits, the words and the name —
 * never the shrinking, which strips EXIF, or the checks, which are the API's own.
 */
/** Shrinking, then checking: a 9 MB photo from a phone is well under the limit once it is the size the Assembly
    will actually store, and refusing it first would be refusing it for a reason that no longer holds. */
function useChosenPhotos({ photos, onChange, limits }: Pick<PhotoFieldProps, "photos" | "onChange" | "limits">) {
  const [problem, setProblem] = useState<string | null>(null);
  const [preparing, setPreparing] = useState(false);
  const choose = async (event: ChangeEvent<HTMLInputElement>) => {
    const chosen = Array.from(event.target.files ?? []);
    event.target.value = ""; // choosing the same photo again still fires a change
    setPreparing(true);
    const ready = await Promise.all(chosen.map(shrink));
    setPreparing(false);
    const picked = addPhotos(photos.map((photo) => photo.file), ready, limits);
    const added = picked.photos.slice(photos.length).map((file) => ({ file, url: URL.createObjectURL(file) }));
    onChange([...photos, ...added]);
    setProblem(picked.problem);
  };
  const remove = (index: number) => {
    URL.revokeObjectURL(photos[index].url);
    onChange(photos.filter((_, i) => i !== index));
    setProblem(null);
  };
  return { choose, remove, problem, preparing };
}

export function PhotoField({ photos, onChange, limits, hint, name = "report", label = "Photos (optional)" }: PhotoFieldProps) {
  const input = useRef<HTMLInputElement>(null);
  useRevokeOnUnmount(photos);
  const { choose, remove, problem, preparing } = useChosenPhotos({ photos, onChange, limits });
  const field = `${name}-photos`;
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={field}>{label}</Label>
      <p className="text-[12.5px] text-ink-soft">
        Up to {limits.maxPhotos} JPEG, PNG or WebP photos, {limitLabel(limits.maxBytes)} each. {hint}
      </p>
      {photos.length > 0 ? (
        <ul className="grid grid-cols-3 gap-2 sm:grid-cols-5" data-testid={field}>
          {photos.map((photo, index) => (
            <Thumb key={photo.url} photo={photo} index={index} onRemove={() => remove(index)} testId={`${name}-photo`} />
          ))}
        </ul>
      ) : null}
      <input ref={input} id={field} type="file" accept={PHOTO_TYPES.join(",")} multiple onChange={(event) => void choose(event)} className="sr-only" data-testid={`${field}-input`} />
      <PhotoButtons count={photos.length} limits={limits} preparing={preparing} onAdd={() => input.current?.click()} testId={`${field}-add`} />
      {problem ? <ErrorNote testId={`${field}-problem`}>{problem}</ErrorNote> : null}
    </div>
  );
}

type ButtonsProps = { count: number; limits: PhotoLimits; preparing: boolean; onAdd: () => void; testId: string };

function PhotoButtons({ count, limits, preparing, onAdd, testId }: ButtonsProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button type="button" variant="secondary" onClick={onAdd} disabled={preparing || count >= limits.maxPhotos} data-testid={testId}>
        <ImagePlusIcon data-icon="inline-start" />
        {count ? "Add more photos" : "Add photos"}
      </Button>
      {preparing ? <span className="text-[12.5px] text-ink-soft" role="status">Preparing the photos…</span> : null}
      {count ? <span className="text-[12.5px] text-ink-soft">{count} of {limits.maxPhotos}</span> : null}
    </div>
  );
}
