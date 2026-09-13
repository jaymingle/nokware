"use client";

import { useState, type FormEvent } from "react";

/**
 * State for a form that sends one PDF plus its fields as multipart: the chosen
 * file, a "no file yet" flag, and the result once sent. Errors stay on the
 * caller's mutation, which `send` wraps.
 */
export function usePdfForm<T>(send: (form: FormData) => Promise<T>) {
  const [file, setFile] = useState<File | null>(null);
  const [fileMissing, setFileMissing] = useState(false);
  const [result, setResult] = useState<T | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setFileMissing(true);
      return;
    }
    const form = new FormData(event.currentTarget);
    form.set("file", file);
    try {
      setResult(await send(form));
      setFile(null);
    } catch {
      // the caller's mutation holds and shows the error
    }
  }

  function chooseFile(next: File | null) {
    setFile(next);
    setFileMissing(false);
  }

  return { file, chooseFile, fileMissing, result, clearResult: () => setResult(null), onSubmit };
}
