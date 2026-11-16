import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router';

import { Dialog } from '@/components/Dialog';
import { Field } from '@/components/Field';
import { FormMessage } from '@/components/FormMessage';
import { PageHeader } from '@/components/PageHeader';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Card, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { meQueryKey, useMe, type Me } from '@/features/auth/session';
import { MIN_PASSWORD_LENGTH } from '@/features/auth/password';
import { api, downloadUrl } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';

import { TwoFactorCard } from './TwoFactorCard';

/** The signed-in person's own account, for planners (/app/account) and couples. */
export function AccountPage({ area }: { area: 'app' | 'portal' }) {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const [params] = useSearchParams();
  if (!me) return <Spinner />;
  return (
    <div className="flex max-w-2xl flex-col gap-6">
      {area === 'app' ? (
        <PageHeader title={t('account.title')} />
      ) : (
        <h1 className="font-display text-4xl font-medium">{t('account.title')}</h1>
      )}
      {area === 'portal' && (
        <nav className="flex flex-wrap gap-4 text-sm font-medium text-accent">
          <Link to="/portal/notifications">{t('notifications.title')}</Link>
          <Link to="/portal/privacy">{t('privacy.title')}</Link>
        </nav>
      )}
      <ProfileCard me={me} />
      <PasswordCard />
      <TwoFactorCard required={params.get('required') === '2fa'} />
      <DataCard area={area} />
    </div>
  );
}

function ProfileCard({ me }: { me: Me }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [name, setName] = useState(me.full_name);
  const save = useMutation({
    mutationFn: () => api<Me>('PATCH', '/me', { full_name: name.trim() }),
    onSuccess: (data) => queryClient.setQueryData(meQueryKey, data),
  });
  return (
    <Card>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <CardTitle>{t('account.profile')}</CardTitle>
        <Field id="account-email" label={t('auth.fields.email')}>
          <Input id="account-email" value={me.email} disabled />
        </Field>
        <Field id="account-name" label={t('auth.fields.fullName')}>
          <Input
            id="account-name"
            required
            maxLength={200}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        {save.isSuccess && <FormMessage tone="success">{t('settings.saved')}</FormMessage>}
        {save.error && <FormMessage>{errorMessage(save.error, t)}</FormMessage>}
        <div>
          <Button type="submit" disabled={save.isPending || name.trim() === me.full_name}>
            {t('common.save')}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function PasswordCard() {
  const { t } = useTranslation();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const save = useMutation({
    mutationFn: () =>
      api('POST', '/me/password', { current_password: current, new_password: next }),
    onSuccess: () => {
      setCurrent('');
      setNext('');
    },
  });
  return (
    <Card>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <CardTitle>{t('account.password')}</CardTitle>
        <Field id="current-password" label={t('account.currentPassword')}>
          <Input
            id="current-password"
            type="password"
            autoComplete="current-password"
            required
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
        </Field>
        <Field
          id="new-password"
          label={t('auth.fields.newPassword')}
          hint={t('auth.fields.passwordHint', { count: MIN_PASSWORD_LENGTH })}
        >
          <Input
            id="new-password"
            type="password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
        </Field>
        {save.isSuccess && <FormMessage tone="success">{t('account.passwordChanged')}</FormMessage>}
        {save.error && <FormMessage>{errorMessage(save.error, t)}</FormMessage>}
        <div>
          <Button type="submit" disabled={save.isPending}>
            {t('account.changePassword')}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function DataCard({ area }: { area: 'app' | 'portal' }) {
  const { t } = useTranslation();
  const [deleting, setDeleting] = useState(false);
  return (
    <Card className="flex flex-col gap-4">
      <CardTitle>{t('account.data.title')}</CardTitle>
      <p className="text-sm text-ink-soft">{t('account.data.exportBody')}</p>
      <div>
        <Button asChild variant="secondary">
          <a href={downloadUrl('/me/export')} download>
            {t('account.data.export')}
          </a>
        </Button>
      </div>
      <div className="border-t border-line pt-4">
        <p className="text-sm text-ink-soft">
          {area === 'portal' ? t('account.data.deleteBodyCouple') : t('account.data.deleteBody')}
        </p>
        <Button variant="ghost" className="mt-2 text-danger" onClick={() => setDeleting(true)}>
          {t('account.data.delete')}
        </Button>
      </div>
      {deleting && <DeleteDialog onClose={() => setDeleting(false)} />}
    </Card>
  );
}

function DeleteDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const remove = useMutation({
    mutationFn: () => api('POST', '/me/delete', { password, confirm }),
    onSuccess: () => {
      queryClient.clear();
      queryClient.setQueryData(meQueryKey, null);
      void navigate('/login', { replace: true });
    },
  });
  return (
    <Dialog title={t('account.data.deleteTitle')} onClose={onClose}>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          remove.mutate();
        }}
      >
        <p className="text-sm text-ink-soft">{t('account.data.deleteWarning')}</p>
        <Field id="delete-password" label={t('auth.fields.password')}>
          <Input
            id="delete-password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <Field id="delete-confirm" label={t('account.data.typeDelete')}>
          <Input
            id="delete-confirm"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
        </Field>
        {remove.error && <FormMessage>{errorMessage(remove.error, t)}</FormMessage>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            type="submit"
            className="bg-danger hover:bg-danger"
            disabled={remove.isPending || confirm !== 'DELETE'}
          >
            {t('account.data.deleteForGood')}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
