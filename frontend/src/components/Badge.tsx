import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

export function Badge({
  tone = 'neutral',
  children,
}: {
  tone?: 'neutral' | 'accent' | 'warning' | 'danger';
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium whitespace-nowrap',
        tone === 'neutral' && 'bg-subtle text-ink-soft',
        tone === 'accent' && 'bg-accent-soft text-accent-strong',
        tone === 'warning' && 'bg-warning-soft text-warning',
        tone === 'danger' && 'bg-danger-soft text-danger',
      )}
    >
      {children}
    </span>
  );
}
