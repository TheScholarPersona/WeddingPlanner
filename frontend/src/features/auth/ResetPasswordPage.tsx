import { useMutation } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router';

import { FormMessage } from '@/components/FormMessage';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { api } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';

import { AuthLayout } from './AuthLayout';
import { MIN_PASSWORD_LENGTH } from './password';

export function ResetPasswordPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const [password, setPassword] = useState('');
  const reset = useMutation({
    mutationFn: () => api('POST', '/auth/password/reset', { token, password }),
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    reset.mutate();
  }

  return (
    <AuthLayout title={t('auth.reset.title')} subtitle={t('auth.reset.subtitle')}>
      {reset.isSuccess ? (
        <>
          <FormMessage tone="success">{t('auth.reset.done')}</FormMessage>
          <Button asChild>
            <Link to="/login">{t('auth.login.submit')}</Link>
          </Button>
        </>
      ) : (
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <Label htmlFor="password">{t('auth.fields.newPassword')}</Label>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              minLength={MIN_PASSWORD_LENGTH}
              required
              aria-describedby="password-hint"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <p id="password-hint" className="text-xs text-muted">
              {t('auth.fields.passwordHint', { count: MIN_PASSWORD_LENGTH })}
            </p>
          </div>
          {reset.isError && <FormMessage>{errorMessage(reset.error, t)}</FormMessage>}
          <Button type="submit" disabled={reset.isPending || !token}>
            {t('auth.reset.submit')}
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}
