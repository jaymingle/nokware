"use client";

import { CheckIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ErrorNote } from "@/components/documents/panels";
import { NameChoice } from "@/components/petitions/name-choice";
import { PhoneConfirm, PhoneConfirmed } from "@/components/petitions/phone-confirm";
import { Button } from "@/components/ui/button";
import { usePhoneProof, type PhoneProof } from "@/hooks/use-phone-proof";
import { useMySignature, useSignPetition, useTakeNameOff } from "@/lib/api/petition-queries";
import { nameNote, signaturesLine, type KeptProof } from "@/lib/petitions";
import { joinNames } from "@/lib/text";

import type { MySignature, PetitionDetail, SignResult } from "@/lib/api/types";

function Signed({ code, signature, proof }: { code: string; signature: MySignature; proof: string }) {
  const takeOff = useTakeNameOff(code);
  return (
    <div className="flex flex-col gap-2" data-testid="sign-done">
      <p className="flex items-center gap-2 text-[15px] font-medium text-teal"><CheckIcon aria-hidden className="size-4" /> You signed this petition</p>
      <p className="text-[13.5px] text-ink-soft">
        {signature.named ? `Your name is shown publicly: ${signature.name}.` : "Anonymously: you're counted, and your name isn't shown."}
      </p>
      {signature.named ? (
        <Button variant="secondary" size="sm" className="w-fit" disabled={takeOff.isPending} onClick={() => takeOff.mutate(proof)} data-testid="sign-take-name-off">
          Take my name off
        </Button>
      ) : null}
      {takeOff.error ? <ErrorNote>{takeOff.error.message}</ErrorNote> : null}
    </div>
  );
}

function useSigning(petition: PetitionDetail, phone: PhoneProof) {
  const [named, setNamed] = useState(false);
  const [name, setName] = useState("");
  const [confirming, setConfirming] = useState(false);
  const sign = useSignPetition(petition.code);
  const send = (proof: string) => sign.mutate({ choice: { show_name: named, name: named ? name : null }, proof }, {
    onSuccess: (result: SignResult) => {
      toast.success(result.added ? `Signed. ${signaturesLine(result.signatures, result.threshold)}.` : "This number had already signed.");
    },
  });
  const onConfirmed = (proof: KeptProof) => {
    phone.confirm(proof);
    setConfirming(false);
    send(proof.token);
  };
  const [missingName, setMissingName] = useState(false);
  const start = () => {
    setMissingName(named && !name.trim()); // asked before the number is confirmed, not after
    if (named && !name.trim()) return;
    if (phone.proof) send(phone.proof.token);
    else setConfirming(true);
  };
  return { named, setNamed, name, setName, confirming, sign, onConfirmed, start, missingName };
}

function Unsigned({ petition, phone }: { petition: PetitionDetail; phone: PhoneProof }) {
  const s = useSigning(petition, phone);
  return (
    <div className="flex flex-col gap-4" data-testid="sign-form">
      <NameChoice named={s.named} setNamed={s.setNamed} name={s.name} setName={s.setName} testId="sign-name"
        anonymousHint="You're counted; your name isn't shown." note={nameNote(joinNames(petition.departments))} />
      {phone.proof && !s.confirming ? <PhoneConfirmed proof={phone.proof} onForget={phone.forget} /> : null}
      {s.confirming ? (
        <PhoneConfirm onConfirmed={s.onConfirmed} lead="Confirm your number to sign. One signature per number: it signs as soon as it's confirmed." />
      ) : (
        <Button className="w-fit" disabled={s.sign.isPending} onClick={s.start} data-testid="sign-submit">
          {s.sign.isPending ? "Signing…" : "Sign this petition"}
        </Button>
      )}
      {s.missingName ? <ErrorNote testId="sign-missing-name">Enter the name to show, or choose to stay anonymous.</ErrorNote> : null}
      {s.sign.error ? <ErrorNote testId="sign-error">{s.sign.error.message}</ErrorNote> : null}
    </div>
  );
}

/** Sign the petition with a confirmed number: anonymous unless the signer chooses to show a name. */
export function SignPanel({ petition }: { petition: PetitionDetail }) {
  const phone = usePhoneProof();
  const mine = useMySignature(petition.code, phone.proof?.token ?? null);
  if (!phone.ready) return null;
  return (
    <section className="flex flex-col gap-3 rounded-xl border bg-card p-5" data-testid="petition-sign">
      <h2 className="text-[19px]">Sign this petition</h2>
      {mine.data?.signed && phone.proof ? <Signed code={petition.code} signature={mine.data} proof={phone.proof.token} /> : <Unsigned petition={petition} phone={phone} />}
    </section>
  );
}
