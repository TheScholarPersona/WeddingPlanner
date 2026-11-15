import { cn } from '@/lib/utils';

export function FormMessage({
  tone = 'error',
  children,
}: {
  tone?: 'error' | 'success';
  children: React.ReactNode;
}) {
  return (
    <p
      role={tone === 'error' ? 'alert' : 'status'}
      className={cn(
        'rounded-lg p-3 text-sm',
        tone === 'error' ? 'bg-danger-soft text-danger' : 'bg-accent-soft text-accent-strong',
      )}
    >
      {children}
    </p>
  );
}

export function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="text-xs text-danger">
      {message}
    </p>
  );
}
