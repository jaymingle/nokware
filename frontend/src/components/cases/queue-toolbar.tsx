"use client";

import { MY_FILTERS, ORDERS, type MyFilterKey, type OrderKey } from "@/lib/cases";
import { cn } from "@/lib/utils";

const CHIP = "rounded-lg border px-3 py-1.5 text-[12.5px] transition-colors";

function Chip({ pressed, onClick, testId, children }: { pressed: boolean; onClick: () => void; testId: string; children: string }) {
  return (
    <button type="button" aria-pressed={pressed} onClick={onClick} data-touch-target
      className={cn(CHIP, pressed ? "border-teal bg-teal-tint font-medium text-teal" : "bg-card text-ink hover:border-teal")}
      data-testid={testId}>
      {children}
    </button>
  );
}

type ToolbarProps = {
  filter: MyFilterKey;
  order: OrderKey;
  onFilter: (filter: MyFilterKey) => void;
  onOrder: (order: OrderKey) => void;
};

export function QueueToolbar({ filter, order, onFilter, onOrder }: ToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Show">
        {(Object.keys(MY_FILTERS) as MyFilterKey[]).map((key) => (
          <Chip key={key} pressed={filter === key} onClick={() => onFilter(key)} testId={`queue-filter-${key}`}>
            {MY_FILTERS[key].label}
          </Chip>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2 ps-1" role="group" aria-label="Order">
        {(Object.keys(ORDERS) as OrderKey[]).map((key) => (
          <Chip key={key} pressed={order === key} onClick={() => onOrder(key)} testId={`queue-order-${key}`}>
            {ORDERS[key].label}
          </Chip>
        ))}
      </div>
    </div>
  );
}
