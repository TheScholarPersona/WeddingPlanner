import { cn } from '@/lib/utils';

export function StatTile({
  label,
  value,
  hint,
  tone = 'default',
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: 'default' | 'danger' | 'warning';
}) {
  return (
    <div className="flex flex-col gap-1.5 rounded-[var(--radius-card)] border border-line bg-surface px-6 py-5">
      <span className="text-sm text-muted">{label}</span>
      <span
        className={cn(
          'font-display text-[40px] leading-none font-semibold',
          tone === 'danger' && 'text-danger',
          tone === 'warning' && 'text-warning',
        )}
      >
        {value}
      </span>
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </div>
  );
}
