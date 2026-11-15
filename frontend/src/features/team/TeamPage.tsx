import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { FormMessage } from '@/components/FormMessage';
import { Spinner } from '@/components/Spinner';
import { Card, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useActiveOrg } from '@/features/auth/useActiveOrg';
import { api, type Schemas } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { formatDate } from '@/lib/format';

import { useReauth } from './useReauth';

type Member = Schemas['MemberOut'];
type Invitation = Schemas['InvitationOut'];
type TeamRole = 'org_admin' | 'member';

export function TeamPage() {
  const { t } = useTranslation();
  const { membership, isAdmin } = useActiveOrg();
  const orgId = membership.organization_id;
  const queryClient = useQueryClient();
  const { run, dialog } = useReauth();
  const [actionError, setActionError] = useState<unknown>(null);

  const members = useQuery({
    queryKey: ['org', orgId, 'members'],
    queryFn: () => api<Member[]>('GET', `/orgs/${orgId}/members`),
  });
  const invitations = useQuery({
    queryKey: ['org', orgId, 'invitations'],
    queryFn: () => api<Invitation[]>('GET', `/orgs/${orgId}/invitations`),
    enabled: isAdmin,
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['org', orgId] });

  async function updateMember(member: Member, change: { role?: TeamRole; status?: string }) {
    setActionError(null);
    try {
      await run(() => api('PATCH', `/orgs/${orgId}/members/${member.id}`, change));
      await refresh();
    } catch (error) {
      setActionError(error);
    }
  }

  async function invitationAction(invitation: Invitation, action: 'resend' | 'revoke') {
    setActionError(null);
    try {
      if (action === 'resend') {
        await api('POST', `/orgs/${orgId}/invitations/${invitation.id}/resend`);
      } else {
        await api('DELETE', `/orgs/${orgId}/invitations/${invitation.id}`);
      }
      await refresh();
    } catch (error) {
      setActionError(error);
    }
  }

  const team = (members.data ?? []).filter((m) => m.role !== 'client');
  const clients = (members.data ?? []).filter((m) => m.role === 'client');

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-1">
        <h1 className="font-display text-[44px] leading-tight font-medium">{t('team.title')}</h1>
        <p className="text-sm text-muted">{t('team.subtitle')}</p>
      </header>

      {actionError !== null && <FormMessage>{errorMessage(actionError, t)}</FormMessage>}

      {isAdmin && <InviteForm orgId={orgId} onInvited={refresh} />}

      <Card className="flex flex-col gap-2 overflow-x-auto">
        <CardTitle>{t('team.members')}</CardTitle>
        {members.isPending ? (
          <Spinner />
        ) : (
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead className="text-xs tracking-wide text-muted uppercase">
              <tr>
                <th className="py-3 font-semibold">{t('team.columns.name')}</th>
                <th className="py-3 font-semibold">{t('team.columns.role')}</th>
                <th className="py-3 font-semibold">{t('team.columns.status')}</th>
                {isAdmin && (
                  <th className="py-3 font-semibold">
                    <span className="sr-only">{t('team.columns.actions')}</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {team.map((member) => (
                <tr key={member.id} className="border-t border-line-soft">
                  <td className="py-3">
                    <div className="font-medium">
                      {member.full_name}
                      {member.is_you && (
                        <span className="ml-2 text-xs text-muted">{t('team.you')}</span>
                      )}
                    </div>
                    <div className="text-xs text-muted">{member.email}</div>
                  </td>
                  <td className="py-3">
                    {isAdmin && !member.is_you ? (
                      <select
                        aria-label={t('team.changeRoleFor', { name: member.full_name })}
                        className="h-9 rounded-lg border border-line bg-surface px-2"
                        value={member.role}
                        onChange={(e) =>
                          void updateMember(member, { role: e.target.value as TeamRole })
                        }
                      >
                        <option value="org_admin">{t('roles.org_admin')}</option>
                        <option value="member">{t('roles.member')}</option>
                      </select>
                    ) : (
                      t(`roles.${member.role}`)
                    )}
                  </td>
                  <td className="py-3">{t(`team.status.${member.status}`)}</td>
                  {isAdmin && (
                    <td className="py-3 text-right">
                      {!member.is_you && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() =>
                            void updateMember(member, {
                              status: member.status === 'active' ? 'disabled' : 'active',
                            })
                          }
                        >
                          {member.status === 'active' ? t('team.deactivate') : t('team.reactivate')}
                        </Button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {isAdmin && (
        <Card className="flex flex-col gap-2">
          <CardTitle>{t('team.pendingInvitations')}</CardTitle>
          {invitations.data?.length ? (
            <ul className="flex flex-col">
              {invitations.data.map((invitation) => (
                <li
                  key={invitation.id}
                  className="flex flex-wrap items-center justify-between gap-3 border-t border-line-soft py-3 text-sm"
                >
                  <div>
                    <div className="font-medium">{invitation.email}</div>
                    <div className="text-xs text-muted">
                      {t(`roles.${invitation.role}`)} ·{' '}
                      {invitation.status === 'expired'
                        ? t('team.invitationExpired')
                        : t('team.invitationValidUntil', {
                            date: formatDate(invitation.expires_at),
                          })}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => void invitationAction(invitation, 'resend')}
                    >
                      {t('team.resend')}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => void invitationAction(invitation, 'revoke')}
                    >
                      {t('team.revoke')}
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">{t('team.noInvitations')}</p>
          )}
        </Card>
      )}

      {isAdmin && clients.length > 0 && (
        <Card className="flex flex-col gap-2">
          <CardTitle>{t('team.clientLogins')}</CardTitle>
          <p className="text-sm text-muted">{t('team.clientLoginsHint')}</p>
          <ul className="flex flex-col">
            {clients.map((client) => (
              <li key={client.id} className="border-t border-line-soft py-3 text-sm">
                <span className="font-medium">{client.full_name}</span>{' '}
                <span className="text-muted">· {client.email}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
      {dialog}
    </div>
  );
}

function InviteForm({ orgId, onInvited }: { orgId: string; onInvited: () => Promise<unknown> }) {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<TeamRole>('member');
  const invite = useMutation({
    mutationFn: () => api<Invitation>('POST', `/orgs/${orgId}/invitations`, { email, role }),
    onSuccess: async () => {
      setEmail('');
      await onInvited();
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    invite.mutate();
  }

  return (
    <Card className="flex flex-col gap-4">
      <CardTitle>{t('team.inviteTitle')}</CardTitle>
      <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3">
        <div className="flex min-w-[220px] flex-[2_1_260px] flex-col gap-2">
          <Label htmlFor="invite-email">{t('auth.fields.email')}</Label>
          <Input
            id="invite-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="flex flex-[1_1_160px] flex-col gap-2">
          <Label htmlFor="invite-role">{t('team.columns.role')}</Label>
          <select
            id="invite-role"
            className="h-11 rounded-[var(--radius-control)] border border-line bg-surface px-3 text-sm"
            value={role}
            onChange={(e) => setRole(e.target.value as TeamRole)}
          >
            <option value="member">{t('roles.member')}</option>
            <option value="org_admin">{t('roles.org_admin')}</option>
          </select>
        </div>
        <Button type="submit" disabled={invite.isPending}>
          {t('team.sendInvitation')}
        </Button>
      </form>
      {invite.isError && <FormMessage>{errorMessage(invite.error, t)}</FormMessage>}
      {invite.isSuccess && <FormMessage tone="success">{t('team.invitationSent')}</FormMessage>}
    </Card>
  );
}
