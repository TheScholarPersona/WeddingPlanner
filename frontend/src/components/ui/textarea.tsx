import type { ComponentProps } from 'react';

import { cn } from '@/lib/utils';

export function Textarea({ className, ...props }: ComponentProps<'textarea'>) {
  return (
    <textarea
      className={cn(
        'min-h-24 w-full rounded-[var(--radius-control)] border border-line bg-surface px-3.5 py-2.5 text-sm text-ink placeholder:text-muted',
        'focus-visible:border-accent',
        className,
      )}
      {...props}
    />
  );
}
