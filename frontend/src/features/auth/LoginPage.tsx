import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export function LoginPage() {
  const { t } = useTranslation();
  const [submitted, setSubmitted] = useState(false);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Authentication is implemented in Sprint 1; the form is final.
    setSubmitted(true);
  }

  return (
    <main id="main" className="flex min-h-screen items-center justify-center bg-ground px-4 py-12">
      <div className="flex w-full max-w-sm flex-col gap-8">
        <header className="flex flex-col gap-2 text-center">
          <h1 className="font-display text-5xl font-medium">{t('auth.login.title')}</h1>
          <p className="text-sm text-muted">{t('auth.login.subtitle')}</p>
        </header>
        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-5 rounded-[var(--radius-card)] border border-line bg-surface p-6"
          noValidate
        >
          <div className="flex flex-col gap-2">
            <Label htmlFor="email">{t('auth.login.email')}</Label>
            <Input id="email" name="email" type="email" autoComplete="email" required />
          </div>
          <div className="flex flex-col gap-2">
            <div className="flex items-baseline justify-between">
              <Label htmlFor="password">{t('auth.login.password')}</Label>
              <Link to="/forgot-password" className="text-xs font-medium text-accent">
                {t('auth.login.forgotPassword')}
              </Link>
            </div>
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
            />
          </div>
          <Button type="submit">{t('auth.login.submit')}</Button>
          {submitted && (
            <p role="status" className="rounded-lg bg-accent-soft p-3 text-sm text-accent-strong">
              {t('auth.login.notAvailableYet')}
            </p>
          )}
        </form>
        <div className="flex justify-center gap-6 text-sm">
          <Link to="/app" className="font-medium text-accent">
            {t('auth.login.explorePlanner')}
          </Link>
          <Link to="/portal" className="font-medium text-accent">
            {t('auth.login.explorePortal')}
          </Link>
        </div>
      </div>
    </main>
  );
}
