import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router';

import { Badge } from '@/components/Badge';
import { FormMessage } from '@/components/FormMessage';
import { PageHeader } from '@/components/PageHeader';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { useActiveOrg } from '@/features/auth/useActiveOrg';
import { keys } from '@/features/weddings/api';
import { api, type Schemas } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { describeOffset } from '@/lib/format';

type TemplateDetail = Schemas['TemplateDetailOut'];
type Item = Schemas['TemplateItemOut'];

/** Offsets are edited in weeks before the wedding; stored as days. */
const toWeeks = (days: number) => String(Math.round(-days / 7));
const toDays = (weeks: string) => -Math.round(Number(weeks) * 7);

export function TemplatePage() {
  const { t } = useTranslation();
  const { id = '' } = useParams();
  const { membership, isAdmin } = useActiveOrg();
  const org = membership.organization_id;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const path = `/orgs/${org}/templates/${id}`;
  const template = useQuery({
    queryKey: keys.template(org, id),
    queryFn: () => api<TemplateDetail>('GET', path),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['org', org] });

  const makeDefault = useMutation({
    mutationFn: () => api('PATCH', path, { is_default: true }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: () => api('DELETE', path),
    onSuccess: async () => {
      await refresh();
      void navigate('/app/templates');
    },
  });
  const removeItem = useMutation({
    mutationFn: (itemId: string) => api('DELETE', `${path}/items/${itemId}`),
    onSuccess: refresh,
  });

  if (template.isPending) return <Spinner />;
  if (!template.data) return <FormMessage>{errorMessage(template.error, t)}</FormMessage>;
  const data = template.data;
  const milestones = data.items
    .filter((i) => i.kind === 'milestone')
    .sort((a, b) => a.offset_days - b.offset_days);
  const tasksOf = (milestoneId: string | null) =>
    data.items
      .filter((i) => i.kind === 'task' && (i.parent_item_id ?? null) === milestoneId)
      .sort((a, b) => a.offset_days - b.offset_days);
  const loose = tasksOf(null);
  const error = makeDefault.error ?? remove.error ?? removeItem.error;

  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <PageHeader
        eyebrow={<Link to="/app/templates">{t('templates.title')}</Link>}
        title={data.name}
        subtitle={
          <span className="flex items-center gap-3">
            {data.is_default && <Badge tone="accent">{t('templates.default')}</Badge>}
            {t('templates.counts', { milestones: data.milestone_count, tasks: data.task_count })}
          </span>
        }
        actions={
          isAdmin && (
            <>
              {!data.is_default && (
                <Button variant="secondary" onClick={() => makeDefault.mutate()}>
                  {t('templates.makeDefault')}
                </Button>
              )}
              <Button
                variant="ghost"
                onClick={() => {
                  if (window.confirm(t('templates.confirmDelete', { name: data.name }))) {
                    remove.mutate();
                  }
                }}
              >
                {t('common.delete')}
              </Button>
            </>
          )
        }
      />
      <p className="text-sm text-muted">{t('templates.explainer')}</p>
      {error && <FormMessage>{errorMessage(error, t)}</FormMessage>}

      {milestones.map((milestone) => (
        <Card key={milestone.id} className="flex flex-col gap-2">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-display text-2xl font-semibold">{milestone.title}</h2>
            <span className="flex items-center gap-2 text-sm text-muted">
              {describeOffset(milestone.offset_days)}
              {isAdmin && (
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={t('templates.removeItem', { title: milestone.title })}
                  onClick={() => removeItem.mutate(milestone.id)}
                >
                  {t('common.remove')}
                </Button>
              )}
            </span>
          </div>
          <ItemList items={tasksOf(milestone.id)} canEdit={isAdmin} onRemove={removeItem.mutate} />
          {isAdmin && <AddItemForm path={path} kind="task" parent={milestone} onAdded={refresh} />}
        </Card>
      ))}
      {loose.length > 0 && (
        <Card className="flex flex-col gap-2">
          <h2 className="font-display text-2xl font-semibold">{t('templates.withoutMilestone')}</h2>
          <ItemList items={loose} canEdit={isAdmin} onRemove={removeItem.mutate} />
        </Card>
      )}
      {isAdmin && (
        <Card className="flex flex-col gap-3">
          <h2 className="font-display text-2xl font-semibold">{t('templates.addMilestone')}</h2>
          <AddItemForm path={path} kind="milestone" onAdded={refresh} />
        </Card>
      )}
    </div>
  );
}

function ItemList({
  items,
  canEdit,
  onRemove,
}: {
  items: Item[];
  canEdit: boolean;
  onRemove: (id: string) => void;
}) {
  const { t } = useTranslation();
  if (!items.length) return <p className="text-sm text-muted">{t('templates.noTasks')}</p>;
  return (
    <ul className="flex flex-col">
      {items.map((item) => (
        <li
          key={item.id}
          className="flex flex-wrap items-center justify-between gap-2 border-b border-line-soft py-2.5 text-sm last:border-b-0"
        >
          <span className="flex flex-col">
            <span className="font-medium">{item.title}</span>
            <span className="text-xs text-muted">
              {describeOffset(item.offset_days)} ·{' '}
              {item.assignee_type === 'client' ? t('templates.forCouple') : t('templates.forTeam')}
            </span>
          </span>
          <span className="flex items-center gap-2">
            <Badge tone={item.visibility === 'client' ? 'accent' : 'neutral'}>
              {item.visibility === 'client'
                ? t('templates.sharedWithCouple')
                : t('templates.internal')}
            </Badge>
            {canEdit && (
              <Button
                variant="ghost"
                size="sm"
                aria-label={t('templates.removeItem', { title: item.title })}
                onClick={() => onRemove(item.id)}
              >
                {t('common.remove')}
              </Button>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}

function AddItemForm({
  path,
  kind,
  parent,
  onAdded,
}: {
  path: string;
  kind: 'milestone' | 'task';
  parent?: Item;
  onAdded: () => Promise<unknown>;
}) {
  const { t } = useTranslation();
  const [title, setTitle] = useState('');
  const [weeks, setWeeks] = useState(parent ? toWeeks(parent.offset_days - 14) : '12');
  const [assignee, setAssignee] = useState('team');
  const [visibility, setVisibility] = useState('internal');
  const prefix = parent ? `add-${parent.id}` : 'add-milestone';
  const add = useMutation({
    mutationFn: () =>
      api('POST', `${path}/items`, {
        kind,
        title,
        offset_days: toDays(weeks),
        assignee_type: assignee,
        visibility,
        parent_item_id: parent?.id ?? null,
      }),
    onSuccess: async () => {
      setTitle('');
      await onAdded();
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    add.mutate();
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-2 pt-2">
      <Input
        aria-label={kind === 'task' ? t('templates.newTask') : t('templates.newMilestone')}
        placeholder={kind === 'task' ? t('templates.newTask') : t('templates.newMilestone')}
        className="min-w-0 flex-[3_1_200px]"
        required
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <label className="flex flex-[1_1_120px] items-center gap-2 text-xs text-muted">
        <Input
          id={`${prefix}-weeks`}
          type="number"
          min={-52}
          max={200}
          className="w-20"
          value={weeks}
          onChange={(e) => setWeeks(e.target.value)}
        />
        {t('templates.weeksBefore')}
      </label>
      {kind === 'task' && (
        <Select
          aria-label={t('templates.assignee')}
          className="w-auto"
          value={assignee}
          onChange={(e) => setAssignee(e.target.value)}
        >
          <option value="team">{t('templates.forTeam')}</option>
          <option value="client">{t('templates.forCouple')}</option>
        </Select>
      )}
      <Select
        aria-label={t('templates.visibility')}
        className="w-auto"
        value={visibility}
        onChange={(e) => setVisibility(e.target.value)}
      >
        <option value="internal">{t('templates.internal')}</option>
        <option value="client">{t('templates.sharedWithCouple')}</option>
      </Select>
      <Button type="submit" size="sm" className="h-11" disabled={add.isPending}>
        {t('common.add')}
      </Button>
      {add.isError && (
        <div className="w-full">
          <FormMessage>{errorMessage(add.error, t)}</FormMessage>
        </div>
      )}
    </form>
  );
}
