import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router';

import { Badge } from '@/components/Badge';
import { Dialog } from '@/components/Dialog';
import { Field } from '@/components/Field';
import { FormMessage } from '@/components/FormMessage';
import { PageHeader } from '@/components/PageHeader';
import { ProgressBar } from '@/components/ProgressBar';
import { Spinner } from '@/components/Spinner';
import { StatTile } from '@/components/StatTile';
import { Button } from '@/components/ui/button';
import { Card, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { useActiveOrg } from '@/features/auth/useActiveOrg';
import { ActivityFeed } from '@/features/tasks/ActivityFeed';
import { api } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { formatDate } from '@/lib/format';
import { cn } from '@/lib/utils';

import {
  keys,
  updateWedding,
  weddingPath,
  type Member,
  type Vendor,
  type Wedding,
  type WeddingVendor,
} from './api';
import { CoupleAccess } from './CoupleAccess';
import { WeddingNav } from './WeddingNav';

export function WeddingPage() {
  const { t } = useTranslation();
  const { id = '' } = useParams();
  const { membership } = useActiveOrg();
  const org = membership.organization_id;
  const wedding = useQuery({
    queryKey: keys.wedding(org, id),
    queryFn: () => api<Wedding>('GET', weddingPath(org, id)),
  });

  if (wedding.isPending) return <Spinner />;
  if (!wedding.data) {
    return <FormMessage>{errorMessage(wedding.error, t)}</FormMessage>;
  }
  return <WeddingView wedding={wedding.data} org={org} />;
}

function WeddingView({ wedding, org }: { wedding: Wedding; org: string }) {
  const { t } = useTranslation();
  const can = (perm: string) => wedding.permissions.includes(perm);
  const [editing, setEditing] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['org', org] });

  const archive = useMutation({
    mutationFn: () =>
      api<Wedding>(
        'POST',
        `${weddingPath(org, wedding.id)}/${wedding.status === 'archived' ? 'restore' : 'archive'}`,
      ),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: () => api('DELETE', weddingPath(org, wedding.id)),
    onSuccess: async () => {
      await refresh();
      void navigate('/app/weddings');
    },
  });

  const facts = [
    wedding.wedding_date ? formatDate(wedding.wedding_date) : t('weddings.noDateYet'),
    wedding.venue_name,
    wedding.guest_count_planned != null
      ? t('weddings.guests', { count: wedding.guest_count_planned })
      : null,
  ].filter(Boolean);

  return (
    <div className="flex flex-col gap-7">
      <PageHeader
        eyebrow={
          <>
            <Link to="/app/weddings">{t('weddings.title')}</Link> /{' '}
            <Link to={`/app/clients/${wedding.client_id}`}>{wedding.client_name}</Link>
          </>
        }
        title={wedding.title}
        subtitle={
          <span className="flex flex-wrap items-center gap-x-5 gap-y-1 text-ink-soft">
            {facts.map((fact) => (
              <span key={fact}>{fact}</span>
            ))}
            {wedding.status === 'archived' && <Badge>{t('weddings.status.archived')}</Badge>}
          </span>
        }
        actions={
          <>
            {can('project:update') && (
              <Button variant="secondary" onClick={() => setEditing(true)}>
                {t('weddings.editDetails')}
              </Button>
            )}
            {can('project:archive') && (
              <Button
                variant="secondary"
                disabled={archive.isPending}
                onClick={() => archive.mutate()}
              >
                {wedding.status === 'archived' ? t('weddings.restore') : t('weddings.archive')}
              </Button>
            )}
            {can('project:delete') && (
              <Button
                variant="ghost"
                onClick={() => {
                  if (window.confirm(t('weddings.confirmDelete', { title: wedding.title }))) {
                    remove.mutate();
                  }
                }}
              >
                {t('common.delete')}
              </Button>
            )}
          </>
        }
      />

      <WeddingNav id={wedding.id} />

      {(archive.isError || remove.isError) && (
        <FormMessage>{errorMessage(archive.error ?? remove.error, t)}</FormMessage>
      )}

      <section
        aria-label={t('weddings.status.label')}
        className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-4"
      >
        <StatTile
          label={t('weddings.daysToGoLabel')}
          value={wedding.days_to_go != null && wedding.days_to_go >= 0 ? wedding.days_to_go : '–'}
        />
        <div className="flex flex-col gap-2 rounded-[var(--radius-card)] border border-line bg-surface px-6 py-5">
          <span className="text-sm text-muted">{t('weddings.progress')}</span>
          <span className="font-display text-[40px] leading-none font-semibold">
            {wedding.progress.percent} %
          </span>
          <ProgressBar percent={wedding.progress.percent} label={t('weddings.progress')} />
        </div>
        <StatTile
          label={t('weddings.openTasks')}
          value={wedding.open_tasks}
          hint={t('weddings.openTasksHint', {
            client: wedding.client_tasks_open,
            overdue: wedding.overdue_tasks,
          })}
          tone={wedding.overdue_tasks > 0 ? 'danger' : 'default'}
        />
      </section>

      <div className="flex flex-wrap items-start gap-6">
        <Milestones wedding={wedding} />
        <div className="flex min-w-0 flex-[2_1_320px] flex-col gap-6">
          <Team wedding={wedding} org={org} canManage={can('project:manage_team')} />
          {can('project_vendors:read') && (
            <WeddingVendors wedding={wedding} org={org} canManage={can('project_vendors:manage')} />
          )}
          {can('client_access:manage') && <CoupleAccess org={org} projectId={wedding.id} />}
          <ActivityFeed org={org} projectId={wedding.id} />
        </div>
      </div>

      {(wedding.style_notes || wedding.notes_internal) && (
        <Card className="flex flex-col gap-3">
          <CardTitle>{t('weddings.notes')}</CardTitle>
          {wedding.style_notes && (
            <p className="text-sm whitespace-pre-line">{wedding.style_notes}</p>
          )}
          {wedding.notes_internal && (
            <div className="flex flex-col gap-1">
              <Badge>{t('weddings.internalOnly')}</Badge>
              <p className="text-sm whitespace-pre-line">{wedding.notes_internal}</p>
            </div>
          )}
        </Card>
      )}

      {editing && (
        <EditWeddingDialog wedding={wedding} org={org} onClose={() => setEditing(false)} />
      )}
    </div>
  );
}

function Milestones({ wedding }: { wedding: Wedding }) {
  const { t } = useTranslation();
  return (
    <Card className="flex min-w-0 flex-[3_1_460px] flex-col gap-1">
      <CardTitle className="mb-2">{t('weddings.milestones')}</CardTitle>
      {wedding.milestones.length === 0 && (
        <p className="text-sm text-muted">{t('weddings.noMilestones')}</p>
      )}
      <ol className="flex flex-col">
        {wedding.milestones.map((milestone) => {
          const percent = milestone.task_total
            ? Math.round((milestone.task_done * 100) / milestone.task_total)
            : 0;
          return (
            <li
              key={milestone.id}
              className="grid grid-cols-[24px_minmax(0,1fr)_auto] items-center gap-3.5 border-b border-line-soft py-3 last:border-b-0"
            >
              <span
                aria-hidden="true"
                className={cn(
                  'size-[18px] rounded-full',
                  milestone.completed ? 'bg-accent' : 'border-2 border-line',
                )}
              />
              <span className="flex min-w-0 flex-col gap-1.5">
                <span className="text-sm font-medium">
                  {milestone.title}
                  <span className="sr-only">
                    {milestone.completed ? ` (${t('weddings.done')})` : ''}
                  </span>
                </span>
                {milestone.task_total > 0 && !milestone.completed && (
                  <ProgressBar percent={percent} label={milestone.title} />
                )}
              </span>
              <span className="text-right text-xs text-muted">
                {milestone.task_total > 0 &&
                  t('weddings.tasksDone', {
                    done: milestone.task_done,
                    total: milestone.task_total,
                  })}
                {milestone.due_date && (
                  <span className="block">{formatDate(milestone.due_date)}</span>
                )}
              </span>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

function Team({ wedding, org, canManage }: { wedding: Wedding; org: string; canManage: boolean }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [membershipId, setMembershipId] = useState('');
  const [role, setRole] = useState('planner');
  const members = useQuery({
    queryKey: keys.members(org),
    queryFn: () => api<Member[]>('GET', `/orgs/${org}/members`),
    enabled: canManage,
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: keys.wedding(org, wedding.id) });
  const base = `${weddingPath(org, wedding.id)}/members`;

  const add = useMutation({
    mutationFn: () => api('POST', base, { membership_id: membershipId, project_role: role }),
    onSuccess: async () => {
      setMembershipId('');
      await refresh();
    },
  });
  const change = useMutation({
    mutationFn: ({ id, projectRole }: { id: string; projectRole: string }) =>
      api('PATCH', `${base}/${id}`, { project_role: projectRole }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api('DELETE', `${base}/${id}`),
    onSuccess: refresh,
  });

  const assigned = new Set(wedding.team.map((m) => m.membership_id));
  const available = (members.data ?? []).filter(
    (m) => m.role !== 'client' && m.status === 'active' && !assigned.has(m.id),
  );
  const error = add.error ?? change.error ?? remove.error;

  return (
    <Card className="flex flex-col gap-3">
      <CardTitle>{t('weddings.team')}</CardTitle>
      <ul className="flex flex-col">
        {wedding.team.map((member) => (
          <li
            key={member.id}
            className="flex flex-wrap items-center justify-between gap-2 border-b border-line-soft py-2.5 text-sm last:border-b-0"
          >
            <span className="font-medium">{member.full_name}</span>
            {canManage ? (
              <span className="flex items-center gap-1">
                <Select
                  aria-label={t('weddings.roleFor', { name: member.full_name })}
                  className="h-9 w-auto"
                  value={member.project_role}
                  onChange={(e) => change.mutate({ id: member.id, projectRole: e.target.value })}
                >
                  {(['lead', 'planner', 'viewer'] as const).map((r) => (
                    <option key={r} value={r}>
                      {t(`weddings.roles.${r}`)}
                    </option>
                  ))}
                </Select>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={t('weddings.removeMember', { name: member.full_name })}
                  onClick={() => remove.mutate(member.id)}
                >
                  {t('common.remove')}
                </Button>
              </span>
            ) : (
              <span className="text-muted">
                {t(`weddings.roles.${member.project_role}` as never)}
              </span>
            )}
          </li>
        ))}
      </ul>
      {canManage && available.length > 0 && (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          <Select
            aria-label={t('weddings.addMember')}
            className="min-w-0 flex-[2_1_160px]"
            required
            value={membershipId}
            onChange={(e) => setMembershipId(e.target.value)}
          >
            <option value="">{t('weddings.chooseMember')}</option>
            {available.map((m) => (
              <option key={m.id} value={m.id}>
                {m.full_name}
              </option>
            ))}
          </Select>
          <Select
            aria-label={t('weddings.newMemberRole')}
            className="flex-[1_1_110px]"
            value={role}
            onChange={(e) => setRole(e.target.value)}
          >
            {(['planner', 'viewer', 'lead'] as const).map((r) => (
              <option key={r} value={r}>
                {t(`weddings.roles.${r}`)}
              </option>
            ))}
          </Select>
          <Button type="submit" size="sm" className="h-11" disabled={add.isPending}>
            {t('common.add')}
          </Button>
        </form>
      )}
      {error && <FormMessage>{errorMessage(error, t)}</FormMessage>}
    </Card>
  );
}

function WeddingVendors({
  wedding,
  org,
  canManage,
}: {
  wedding: Wedding;
  org: string;
  canManage: boolean;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [vendorId, setVendorId] = useState('');
  const base = `${weddingPath(org, wedding.id)}/vendors`;
  const linked = useQuery({
    queryKey: keys.weddingVendors(org, wedding.id),
    queryFn: () => api<WeddingVendor[]>('GET', base),
  });
  const directory = useQuery({
    queryKey: keys.vendors(org),
    queryFn: () => api<Vendor[]>('GET', `/orgs/${org}/vendors`),
    enabled: canManage,
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['org', org] });

  const add = useMutation({
    mutationFn: () => api('POST', base, { vendor_id: vendorId }),
    onSuccess: async () => {
      setVendorId('');
      await refresh();
    },
  });
  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api('PATCH', `${base}/${id}`, { status }),
    onSuccess: refresh,
  });

  const linkedIds = new Set(linked.data?.map((v) => v.vendor_id));
  const available = (directory.data ?? []).filter((v) => !linkedIds.has(v.id));

  return (
    <Card className="flex flex-col gap-3">
      <CardTitle>{t('weddings.vendors')}</CardTitle>
      {linked.data?.length === 0 && <p className="text-sm text-muted">{t('weddings.noVendors')}</p>}
      <ul className="flex flex-col">
        {linked.data?.map((vendor) => (
          <li
            key={vendor.id}
            className="flex flex-wrap items-center justify-between gap-2 border-b border-line-soft py-2.5 text-sm last:border-b-0"
          >
            <span className="flex flex-col">
              <span className="font-medium">{vendor.name}</span>
              <span className="text-xs text-muted">
                {t(`vendors.categories.${vendor.category}` as never)}
              </span>
            </span>
            {canManage ? (
              <Select
                aria-label={t('weddings.vendorStatusFor', { name: vendor.name })}
                className="h-9 w-auto"
                value={vendor.status}
                onChange={(e) => setStatus.mutate({ id: vendor.id, status: e.target.value })}
              >
                {(['considered', 'requested', 'booked', 'cancelled'] as const).map((s) => (
                  <option key={s} value={s}>
                    {t(`weddings.vendorStatus.${s}`)}
                  </option>
                ))}
              </Select>
            ) : (
              <Badge tone={vendor.status === 'booked' ? 'accent' : 'neutral'}>
                {t(`weddings.vendorStatus.${vendor.status}`)}
              </Badge>
            )}
          </li>
        ))}
      </ul>
      {canManage && available.length > 0 && (
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          <Select
            aria-label={t('weddings.addVendor')}
            required
            value={vendorId}
            onChange={(e) => setVendorId(e.target.value)}
          >
            <option value="">{t('weddings.chooseVendor')}</option>
            {available.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name} · {t(`vendors.categories.${v.category}`)}
              </option>
            ))}
          </Select>
          <Button type="submit" size="sm" className="h-11" disabled={add.isPending}>
            {t('common.add')}
          </Button>
        </form>
      )}
      {(add.error ?? setStatus.error) && (
        <FormMessage>{errorMessage(add.error ?? setStatus.error, t)}</FormMessage>
      )}
    </Card>
  );
}

function EditWeddingDialog({
  wedding,
  org,
  onClose,
}: {
  wedding: Wedding;
  org: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    title: wedding.title,
    wedding_date: wedding.wedding_date ?? '',
    venue_name: wedding.venue_name ?? '',
    venue_address: wedding.venue_address ?? '',
    guest_count_planned: wedding.guest_count_planned?.toString() ?? '',
    style_notes: wedding.style_notes ?? '',
    notes_internal: wedding.notes_internal ?? '',
  });
  const set = (key: keyof typeof form) => (value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

  const save = useMutation({
    mutationFn: () =>
      updateWedding(org, wedding, {
        title: form.title,
        wedding_date: form.wedding_date || null,
        venue_name: form.venue_name || null,
        venue_address: form.venue_address || null,
        guest_count_planned: form.guest_count_planned ? Number(form.guest_count_planned) : null,
        style_notes: form.style_notes || null,
        notes_internal: form.notes_internal || null,
      }),
    onSuccess: async (updated) => {
      queryClient.setQueryData(keys.wedding(org, wedding.id), updated);
      await queryClient.invalidateQueries({ queryKey: ['org', org, 'weddings'] });
      onClose();
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate();
  }

  return (
    <Dialog title={t('weddings.editDetails')} onClose={onClose}>
      <form onSubmit={handleSubmit} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto">
        <Field id="edit-title" label={t('weddings.fields.title')}>
          <Input
            id="edit-title"
            required
            value={form.title}
            onChange={(e) => set('title')(e.target.value)}
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field id="edit-date" label={t('weddings.fields.weddingDate')}>
            <Input
              id="edit-date"
              type="date"
              value={form.wedding_date}
              onChange={(e) => set('wedding_date')(e.target.value)}
            />
          </Field>
          <Field id="edit-guests" label={t('weddings.fields.guests')}>
            <Input
              id="edit-guests"
              type="number"
              min={0}
              value={form.guest_count_planned}
              onChange={(e) => set('guest_count_planned')(e.target.value)}
            />
          </Field>
        </div>
        <Field id="edit-venue" label={t('weddings.fields.venue')}>
          <Input
            id="edit-venue"
            value={form.venue_name}
            onChange={(e) => set('venue_name')(e.target.value)}
          />
        </Field>
        <Field id="edit-address" label={t('weddings.fields.venueAddress')}>
          <Input
            id="edit-address"
            value={form.venue_address}
            onChange={(e) => set('venue_address')(e.target.value)}
          />
        </Field>
        <Field id="edit-style" label={t('weddings.fields.style')}>
          <Textarea
            id="edit-style"
            value={form.style_notes}
            onChange={(e) => set('style_notes')(e.target.value)}
          />
        </Field>
        <Field
          id="edit-notes"
          label={t('weddings.fields.internalNotes')}
          hint={t('weddings.internalOnly')}
        >
          <Textarea
            id="edit-notes"
            value={form.notes_internal}
            onChange={(e) => set('notes_internal')(e.target.value)}
          />
        </Field>
        {save.isError && <FormMessage>{errorMessage(save.error, t)}</FormMessage>}
        <div className="flex justify-end gap-3">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={save.isPending}>
            {t('common.save')}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
