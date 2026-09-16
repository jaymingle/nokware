"use client";

import { useRef, useState, type DragEvent } from "react";
import { FileTextIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatBytes, pdfProblem } from "@/lib/uploads";

type PdfFieldProps = {
  file: File | null;
  onChange: (file: File | null) => void;
  testId: string;
};

function ChosenFile({ file, onClear, testId }: { file: File; onClear: () => void; testId: string }) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border bg-paper-subtle px-4 py-3">
      <FileTextIcon aria-hidden className="size-5 text-teal" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm" data-testid={`${testId}-name`}>
          {file.name}
        </p>
        <p className="text-[12.5px] text-ink-soft">{formatBytes(file.size)}</p>
      </div>
      <Button variant="ghost" size="sm" onClick={onClear} data-testid={`${testId}-clear`}>
        Choose another
      </Button>
    </div>
  );
}

function DropZone({ onFile, onChoose, testId }: { onFile: (file?: File) => void; onChoose: () => void; testId: string }) {
  const [dragging, setDragging] = useState(false);

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    onFile(event.dataTransfer.files[0]);
  }

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={cn("rounded-xl border border-dashed px-5 py-6 text-center", dragging && "border-teal bg-teal-tint")}
    >
      <p className="text-[15px]">Drop a PDF here</p>
      <p className="mt-1 mb-3.5 text-[12.5px] text-ink-soft">or choose a file · up to 50 MB</p>
      <Button type="button" onClick={onChoose} data-testid={`${testId}-choose`}>
        Choose file
      </Button>
    </div>
  );
}

/** Drop or choose one PDF. Rejected files never reach the form's state. */
export function PdfField({ file, onChange, testId }: PdfFieldProps) {
  const input = useRef<HTMLInputElement>(null);
  const [problem, setProblem] = useState<string | null>(null);

  function take(candidate: File | undefined) {
    if (!candidate) return;
    const reason = pdfProblem(candidate);
    setProblem(reason);
    onChange(reason ? null : candidate);
  }

  return (
    <div className="flex flex-col gap-2">
      {/*
        The control a person uses is the "Choose file" button, which opens this.
        Out of the tab order and out of the accessibility tree together: left in
        the tree it announced as an unnamed file field nobody could operate.
      */}
      <input
        ref={input}
        type="file"
        accept="application/pdf,.pdf"
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        onChange={(event) => take(event.target.files?.[0])}
        data-testid={`${testId}-input`}
      />
      {file ? (
        <ChosenFile file={file} testId={testId} onClear={() => onChange(null)} />
      ) : (
        <DropZone onFile={take} onChoose={() => input.current?.click()} testId={testId} />
      )}
      {problem ? (
        <p role="alert" className="text-[12.5px] text-brick" data-testid={`${testId}-problem`}>
          {problem}
        </p>
      ) : null}
    </div>
  );
}
