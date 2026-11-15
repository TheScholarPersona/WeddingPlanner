import type { ComponentProps } from 'react';

import { cn } from '@/lib/utils';

export function Select({ className, ...props }: ComponentProps<'select'>) {
  return (
    <select
      className={cn(
        'h-11 w-full rounded-[var(--radius-control)] border border-line bg-surface px-3 text-sm text-ink',
        'focus-visible:border-accent',
        className,
      )}
      {...props}
    />
  );
}
