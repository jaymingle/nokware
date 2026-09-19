"use client";

import Image from "next/image";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { ErrorNote } from "@/components/documents/panels";
import { ReportGrounds } from "@/components/petitions/report-grounds";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { useRemovePetitionImage } from "@/lib/api/queries";

import type { PetitionGround, PetitionGroundOption, PetitionImage } from "@/lib/api/types";

const FIRST_GROUND: PetitionGround = "private_individual";

type Props = { code: string; images: PetitionImage[]; grounds: PetitionGroundOption[] };

function RemoveForm({ code, image, grounds, position, onDone }: {
  code: string; image: PetitionImage; grounds: PetitionGroundOption[]; position: number; onDone: () => void;
}) {
  const [ground, setGround] = useState<PetitionGround>(FIRST_GROUND);
  const remove = useRemovePetitionImage();
  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    remove.mutate({ code, imageId: image.id, ground }, {
      onSuccess: () => {
        toast.success("Taken down. The petition and its other photos stand.");
        onDone();
      },
    });
  };
  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <ReportGrounds grounds={grounds} chosen={ground} onChoose={setGround} name={`remove-image-${image.id}`}
        testIdPrefix={`remove-image-${position}-ground`} legend="The ground it comes down on" />
      {remove.error ? <ErrorNote testId={`remove-image-${position}-error`}>{remove.error.message}</ErrorNote> : null}
      <DialogFooter>
        <DialogClose asChild>
          <Button type="button" variant="secondary" data-testid={`remove-image-${position}-cancel`}>Cancel</Button>
        </DialogClose>
        <Button type="submit" disabled={remove.isPending} data-testid={`remove-image-${position}-confirm`}>
          Take this photo down
        </Button>
      </DialogFooter>
    </form>
  );
}

function Photo({ code, image, grounds, position }: {
  code: string; image: PetitionImage; grounds: PetitionGroundOption[]; position: number;
}) {
  const [open, setOpen] = useState(false);
  return (
    <li className="flex flex-col gap-1.5">
      <Image src={image.url} alt={`Photo ${position} on this petition`} width={160} height={120} unoptimized
        className="aspect-4/3 w-full rounded-md border object-cover" />
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger asChild>
          <Button variant="secondary" size="sm" data-testid={`remove-image-${position}`}>Take it down…</Button>
        </DialogTrigger>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-[20px]">Take this photo down?</DialogTitle>
            <DialogDescription>
              The petition stays up with its words, its signatures and its other photos. The trail records that a
              photo came down and on what ground.
            </DialogDescription>
          </DialogHeader>
          {open ? <RemoveForm code={code} image={image} grounds={grounds} position={position} onDone={() => setOpen(false)} /> : null}
        </DialogContent>
      </Dialog>
    </li>
  );
}

/**
 * The photographs on a reported petition. A photograph carrying a number or a face is the commonest reason a
 * petition is reported, and taking the whole petition down for one of them costs its signatures over something
 * its creator could have cropped.
 */
export function ReportedImages({ code, images, grounds }: Props) {
  if (images.length === 0) return null;
  return (
    <div className="flex flex-col gap-2" data-testid={`report-images-${code}`}>
      <p className="text-[13px] text-ink-soft">Photos on this petition</p>
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {images.map((image, index) => (
          <Photo key={image.id} code={code} image={image} grounds={grounds} position={index + 1} />
        ))}
      </ul>
    </div>
  );
}
