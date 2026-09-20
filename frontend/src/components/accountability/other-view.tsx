import { ArrowRightIcon } from "lucide-react";
import Link from "next/link";

/** The two accountability views answer different questions about the same Assembly; each says where the other is. */
export function OtherView({ href, title, children, testId }: { href: string; title: string; children: string; testId: string }) {
  return (
    <Link href={href} data-touch-target
      className="group flex flex-wrap items-baseline gap-x-2 gap-y-1 rounded-xl border border-dashed bg-paper-subtle px-4 py-3 transition-colors hover:border-teal"
      data-testid={testId}>
      <span className="text-[14px] font-medium text-teal">
        {title}
        <ArrowRightIcon aria-hidden className="ms-1.5 inline size-4 transition-transform group-hover:translate-x-0.5" />
      </span>
      <span className="text-[13.5px] text-ink-soft">{children}</span>
    </Link>
  );
}
