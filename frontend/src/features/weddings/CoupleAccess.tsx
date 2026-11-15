import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { FormMessage } from '@/components/FormMessage';
import { Button } from '@/components/ui/button';
import { Card, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { api, type Schemas } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { formatDate } from '@/lib/format';

import { weddingPath } from './api';

type Access = Schemas['ClientAccessOut'];

/** Who of the couple can open the client portal, and invitations to it. */
export function CoupleAccess({ org, projectId }: { org: string; projectId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const base = `${weddingPath(org, projectId)}/client-access`;
  const key = ['org', org, 'wedding', projectId, 'client-access'];
  const [email, setEmail] = useState('');
  const access = useQuery({ queryKey: key, queryFn: () => api<Access>('GET', base) });
  const refresh = () => queryClient.invalidateQueries({ queryKey: key });

  const invite = useMutation({
    mutationFn: () => api<Access>('POST', `${base}/invitations`, { email }),
    onSuccess: (data) => {
      setEmail('');
      queryClient.setQueryData(key, data);
    },
  });
  const revokeInvitation = useMutation({
    mutationFn: (id: string) => api('DELETE', `${base}/invitations/${id}`),
    onSuccess: refresh,
  });
  const revokeLogin = useMutation({
    mutationFn: (id: string) => api('DELETE', `${base}/${id}`),
    onSuccess: refresh,
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    invite.mutate();
  }

  const error = invite.error ?? revokeInvitation.error ?? revokeLogin.error;
  return (
    <Card className="flex flex-col gap-3">
      <CardTitle>{t('couple.title')}</CardTitle>
      <p className="text-sm text-muted">{t('couple.hint')}</p>
      <ul className="flex flex-col">
        {access.data?.logins.map((login) => (
          <li
            key={login.project_member_id}
            className="flex flex-wrap items-center justify-between gap-2 border-b border-line-soft py-2.5 text-sm"
          >
            <span className="flex flex-col">
              <span className="font-medium">{login.full_name}</span>
              <span className="text-xs text-muted">
                {login.last_login_at
                  ? t('couple.lastSeen', { date: formatDate(login.last_login_at) })
                  : login.email}
              </span>
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                if (window.confirm(t('couple.confirmRevoke', { name: login.full_name }))) {
                  revokeLogin.mutate(login.project_member_id);
                }
              }}
            >
              {t('couple.revoke')}
            </Button>
          </li>
        ))}
        {access.data?.invitations.map((invitation) => (
          <li
            key={invitation.id}
            className="flex flex-wrap items-center justify-between gap-2 border-b border-line-soft py-2.5 text-sm"
          >
            <span className="flex flex-col">
              <span className="font-medium">{invitation.email}</span>
              <span className="text-xs text-muted">
                {invitation.expired
                  ? t('team.invitationExpired')
                  : t('couple.invitedUntil', { date: formatDate(invitation.expires_at) })}
              </span>
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => revokeInvitation.mutate(invitation.id)}
            >
              {t('team.revoke')}
            </Button>
          </li>
        ))}
      </ul>
      <form onSubmit={handleSubmit} className="flex gap-2">
        <Input
          type="email"
          aria-label={t('couple.emailLabel')}
          placeholder={t('couple.emailLabel')}
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Button type="submit" size="sm" className="h-11" disabled={invite.isPending}>
          {t('couple.invite')}
        </Button>
      </form>
      {invite.isSuccess && <FormMessage tone="success">{t('couple.sent')}</FormMessage>}
      {error && <FormMessage>{errorMessage(error, t)}</FormMessage>}
    </Card>
  );
}
