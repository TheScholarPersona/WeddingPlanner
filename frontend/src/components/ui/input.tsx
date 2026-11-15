import type { ComponentProps } from 'react';

import { cn } from '@/lib/utils';

export function Input({ className, ...props }: ComponentProps<'input'>) {
  return (
    <input
      className={cn(
        'h-11 w-full rounded-[var(--radius-control)] border border-line bg-surface px-3.5 text-sm text-ink placeholder:text-muted',
        'focus-visible:border-accent focus-visible:outline-2 focus-visible:outline-accent-tint',
        'aria-invalid:border-danger',
        className,
      )}
      {...props}
    />
  );
}
