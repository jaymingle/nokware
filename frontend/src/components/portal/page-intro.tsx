import type { ReactNode } from "react";

/** A page's opening: small eyebrow, Fraunces heading, and an optional lead or aside. */
export function PageIntro({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="mb-7 flex flex-col gap-3">
      <div>
        <div className="text-[12.5px] text-ink-soft">{eyebrow}</div>
        <h1 className="mt-1.5 text-[32px] leading-tight sm:text-[40px]">{title}</h1>
      </div>
      {children ? <div className="max-w-[62ch] text-base text-ink-soft">{children}</div> : null}
    </div>
  );
}
