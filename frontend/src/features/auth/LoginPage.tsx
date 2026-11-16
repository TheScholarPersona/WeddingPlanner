import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router';

import { FormMessage } from '@/components/FormMessage';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { api, ApiError } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';

import { AuthLayout } from './AuthLayout';
import {
  homePathFor,
  meQueryKey,
  needsSecondFactor,
  safeNext,
  useMe,
  type Me,
  type SignInResult,
} from './session';

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const { data: me, isPending } = useMe();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  // An accepted invitation for an account with 2FA arrives here waiting for the code.
  const [step, setStep] = useState<'password' | 'code'>(
    (location.state as { twoFactor?: boolean } | null)?.twoFactor ? 'code' : 'password',
  );

  const finish = (user: Me) => {
    queryClient.setQueryData(meQueryKey, user);
    void navigate(safeNext(params.get('next')) ?? homePathFor(user), { replace: true });
  };
  const login = useMutation({
    mutationFn: () => api<SignInResult>('POST', '/auth/login', { email, password }),
    onSuccess: (result) => (needsSecondFactor(result) ? setStep('code') : finish(result)),
  });

  if (isPending) return <Spinner fullPage />;
  if (me && !login.isPending) return <Navigate to={homePathFor(me)} replace />;
  if (step === 'code') {
    return <SecondFactor onDone={finish} onCancel={() => setStep('password')} />;
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    login.mutate();
  }

  return (
    <AuthLayout title={t('auth.login.title')} subtitle={t('auth.login.subtitle')}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-5">
        <div className="flex flex-col gap-2">
          <Label htmlFor="email">{t('auth.fields.email')}</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-2">
          <div className="flex items-baseline justify-between">
            <Label htmlFor="password">{t('auth.fields.password')}</Label>
            <Link to="/forgot-password" className="text-xs font-medium text-accent">
              {t('auth.login.forgotPassword')}
            </Link>
          </div>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {login.isError && <FormMessage>{errorMessage(login.error, t)}</FormMessage>}
        <Button type="submit" disabled={login.isPending}>
          {login.isPending ? t('auth.login.submitting') : t('auth.login.submit')}
        </Button>
      </form>
    </AuthLayout>
  );
}

function SecondFactor({ onDone, onCancel }: { onDone: (me: Me) => void; onCancel: () => void }) {
  const { t } = useTranslation();
  const [code, setCode] = useState('');
  const verify = useMutation({
    mutationFn: () => api<Me>('POST', '/auth/2fa/verify', { code: code.trim() }),
    onSuccess: onDone,
    onError: (error) => {
      // Too many wrong codes end the attempt; start over with the password.
      if (error instanceof ApiError && error.status === 401) onCancel();
    },
  });
  const cancel = useMutation({
    mutationFn: () => api('POST', '/auth/2fa/cancel'),
    onSettled: onCancel,
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    verify.mutate();
  }

  return (
    <AuthLayout title={t('auth.twoFactor.title')} subtitle={t('auth.twoFactor.subtitle')}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-5">
        <div className="flex flex-col gap-2">
          <Label htmlFor="code">{t('auth.twoFactor.code')}</Label>
          <Input
            id="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            required
            minLength={6}
            maxLength={20}
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
          <p className="text-xs text-muted">{t('auth.twoFactor.recoveryHint')}</p>
        </div>
        {verify.isError && <FormMessage>{errorMessage(verify.error, t)}</FormMessage>}
        <Button type="submit" disabled={verify.isPending}>
          {t('auth.twoFactor.submit')}
        </Button>
        <Button type="button" variant="ghost" onClick={() => cancel.mutate()}>
          {t('auth.twoFactor.cancel')}
        </Button>
      </form>
    </AuthLayout>
  );
}
