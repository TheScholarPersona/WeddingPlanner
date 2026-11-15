import type { ReactNode } from 'react';

export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <main id="main" className="flex min-h-screen items-center justify-center bg-ground px-4 py-12">
      <div className="flex w-full max-w-sm flex-col gap-8">
        <header className="flex flex-col gap-2 text-center">
          <h1 className="font-display text-5xl font-medium">{title}</h1>
          {subtitle && <p className="text-sm text-muted">{subtitle}</p>}
        </header>
        <div className="flex flex-col gap-5 rounded-[var(--radius-card)] border border-line bg-surface p-6">
          {children}
        </div>
        {footer && <div className="flex justify-center gap-6 text-sm">{footer}</div>}
      </div>
    </main>
  );
}
