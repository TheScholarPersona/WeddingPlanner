import type { ComponentProps } from 'react';

import { Input } from '@/components/ui/input';

/** Euro amount input; the value is a decimal string in euros (see toCents/toInput). */
export function MoneyInput(props: Omit<ComponentProps<typeof Input>, 'type'>) {
  return (
    <div className="relative">
      <Input type="number" inputMode="decimal" min={0} step="0.01" className="pr-8" {...props} />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-sm text-muted"
      >
        €
      </span>
    </div>
  );
}
