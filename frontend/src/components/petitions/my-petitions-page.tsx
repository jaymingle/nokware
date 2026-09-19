"use client";

import Link from "next/link";
import { useEffect } from "react";

import { EmptyPanel, ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { PageShell } from "@/components/page-shell";
import { OwnPetitionCard } from "@/components/petitions/own-petition-card";
import { PhoneConfirm, PhoneConfirmed } from "@/components/petitions/phone-confirm";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { usePhoneProof, type PhoneProof } from "@/hooks/use-phone-proof";
import { ApiError } from "@/lib/api/errors";
import { useMyPetitions } from "@/lib/api/petition-queries";

import type { KeptProof } from "@/lib/petitions";

function Mine({ proof, forget }: { proof: KeptProof; forget: () => void }) {
  const mine = useMyPetitions(proof.token);
  const expired = mine.error instanceof ApiError && mine.error.status === 401;
  useEffect(() => {
    if (expired) forget(); // the confirmation ran out: ask for the number again
  }, [expired, forget]);
  return (
    <div className="flex flex-col gap-4">
      <PhoneConfirmed proof={proof} onForget={forget} />
      {mine.isPending ? <LoadingPanel label="Loading your petitions…" /> : null}
      {mine.error ? <ErrorPanel message={mine.error.message} onRetry={() => void mine.refetch()} /> : null}
      {mine.data && mine.data.petitions.length === 0 ? (
        <EmptyPanel title="No petitions from this number">
          <Button asChild size="sm" className="mt-2"><Link href="/petitions/new" data-testid="mine-start">Start a petition</Link></Button>
        </EmptyPanel>
      ) : null}
      {mine.data?.petitions.map((petition) => <OwnPetitionCard key={petition.code} petition={petition} proof={proof.token} />)}
    </div>
  );
}

function Confirm({ phone }: { phone: PhoneProof }) {
  return (
    <Card>
      <CardContent>
        <PhoneConfirm onConfirmed={phone.confirm} lead="Confirm the number you started your petition with, to see it and change it." />
      </CardContent>
    </Card>
  );
}

export function MyPetitionsPage() {
  const phone = usePhoneProof();
  return (
    <PageShell
      eyebrow="Petitions"
      title="Your petitions"
      lead={
        <>
          The petitions you started, with any decision the MCE made and what you can still do. No account: your phone number
          is how Nokware knows they are yours.
        </>
      }
    >
      {!phone.ready ? <LoadingPanel label="Loading…" /> : null}
      {phone.ready && phone.proof ? <Mine proof={phone.proof} forget={phone.forget} /> : null}
      {phone.ready && !phone.proof ? <Confirm phone={phone} /> : null}
    </PageShell>
  );
}
