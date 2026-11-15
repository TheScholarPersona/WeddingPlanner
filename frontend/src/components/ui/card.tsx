import type { ComponentProps } from 'react';

import { cn } from '@/lib/utils';

export function Card({ className, ...props }: ComponentProps<'section'>) {
  return (
    <section
      className={cn('rounded-[var(--radius-card)] border border-line bg-surface p-6', className)}
      {...props}
    />
  );
}

export function CardTitle({ className, children, ...props }: ComponentProps<'h2'>) {
  return (
    <h2 className={cn('font-display text-[26px] font-semibold', className)} {...props}>
      {children}
    </h2>
  );
}
