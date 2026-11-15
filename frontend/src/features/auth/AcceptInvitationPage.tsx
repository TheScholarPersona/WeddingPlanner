import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router';

import { FieldError, FormMessage } from '@/components/FormMessage';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { api, type Schemas } from '@/lib/api/client';
import { errorMessage, fieldErrors } from '@/lib/api/errors';

import { AuthLayout } from './AuthLayout';
import { MIN_PASSWORD_LENGTH } from './password';
import { homePathFor, meQueryKey, type Me } from './session';

type InvitationInfo = Schemas['InvitationInfoOut'];

export function AcceptInvitationPage() {
  const { t } = useTranslation();
  const { token = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');

  const info = useQuery({
    queryKey: ['invitation', token],
    queryFn: () => api<InvitationInfo>('GET', `/auth/invitations/${encodeURIComponent(token)}`),
    retry: false,
  });

  const accept = useMutation({
    mutationFn: () =>
      api<Me>('POST', `/auth/invitations/${encodeURIComponent(token)}/accept`, {
        full_name: info.data?.account_exists ? null : fullName,
        password,
      }),
    onSuccess: (me) => {
      queryClient.setQueryData(meQueryKey, me);
      void navigate(homePathFor(me), { replace: true });
    },
  });

  if (info.isPending) return <Spinner fullPage />;
  if (info.isError || !info.data) {
    return (
      <AuthLayout
        title={t('auth.invite.invalidTitle')}
        footer={
          <Link to="/login" className="font-medium text-accent">
            {t('auth.backToLogin')}
          </Link>
        }
      >
        <FormMessage>{errorMessage(info.error, t)}</FormMessage>
      </AuthLayout>
    );
  }

  const { organization_name: organization, email, account_exists: existing } = info.data;
  const errors = fieldErrors(accept.error);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    accept.mutate();
  }

  return (
    <AuthLayout
      title={t('auth.invite.title')}
      subtitle={t(
        info.data.role === 'client'
          ? 'auth.invite.subtitleCouple'
          : existing
            ? 'auth.invite.subtitleExisting'
            : 'auth.invite.subtitleNew',
        { organization },
      )}
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-5">
        <div className="flex flex-col gap-2">
          <Label htmlFor="email">{t('auth.fields.email')}</Label>
          <Input id="email" type="email" value={email} readOnly disabled />
        </div>
        {!existing && (
          <div className="flex flex-col gap-2">
            <Label htmlFor="full-name">{t('auth.fields.fullName')}</Label>
            <Input
              id="full-name"
              autoComplete="name"
              required
              value={fullName}
              aria-invalid={!!errors.full_name}
              aria-describedby="full-name-error"
              onChange={(e) => setFullName(e.target.value)}
            />
            <FieldError id="full-name-error" message={errors.full_name} />
          </div>
        )}
        <div className="flex flex-col gap-2">
          <Label htmlFor="password">
            {existing ? t('auth.fields.password') : t('auth.fields.choosePassword')}
          </Label>
          <Input
            id="password"
            type="password"
            autoComplete={existing ? 'current-password' : 'new-password'}
            minLength={existing ? undefined : MIN_PASSWORD_LENGTH}
            required
            value={password}
            aria-invalid={!!errors.password}
            aria-describedby="password-hint"
            onChange={(e) => setPassword(e.target.value)}
          />
          <p id="password-hint" className="text-xs text-muted">
            {existing
              ? t('auth.invite.existingHint')
              : t('auth.fields.passwordHint', { count: MIN_PASSWORD_LENGTH })}
          </p>
        </div>
        {accept.isError && !Object.keys(errors).length && (
          <FormMessage>{errorMessage(accept.error, t)}</FormMessage>
        )}
        <Button type="submit" disabled={accept.isPending}>
          {info.data.role === 'client'
            ? t('auth.invite.openPortal')
            : t('auth.invite.submit', { organization })}
        </Button>
      </form>
    </AuthLayout>
  );
}
