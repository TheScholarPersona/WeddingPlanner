import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';

import { FormMessage } from '@/components/FormMessage';
import { PageHeader } from '@/components/PageHeader';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { useActiveOrg } from '@/features/auth/useActiveOrg';
import { keys, weddingPath, type Wedding } from '@/features/weddings/api';
import { WeddingNav } from '@/features/weddings/WeddingNav';
import { api } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { formatDate } from '@/lib/format';
import { cn } from '@/lib/utils';

import { projectPath, taskKeys, type Milestone, type Task } from './api';
import { TaskDialog } from './TaskDialog';
import { TaskRow } from './TaskRow';

type Filter = 'open' | 'done' | 'client' | 'internal' | 'mine' | 'all';
const FILTERS: Filter[] = ['open', 'mine', 'client', 'internal', 'done', 'all'];

function query(filter: Filter): string {
  switch (filter) {
    case 'open':
      return 'status=open';
    case 'done':
      return 'status=done';
    case 'client':
      return 'assignee=client';
    case 'internal':
      return 'visibility=internal';
    case 'mine':
      return 'assignee=me';
    default:
      return '';
  }
}

export function WeddingTasksPage() {
  const { t } = useTranslation();
  const { id = '' } = useParams();
  const { membership } = useActiveOrg();
  const org = membership.organization_id;
  const [filter, setFilter] = useState<Filter>('open');
  const [openTask, setOpenTask] = useState<string | null>(null);

  const wedding = useQuery({
    queryKey: keys.wedding(org, id),
    queryFn: () => api<Wedding>('GET', weddingPath(org, id)),
  });
  const milestones = useQuery({
    queryKey: taskKeys.milestones(org, id),
    queryFn: () => api<Milestone[]>('GET', `${projectPath(org, id)}/milestones`),
  });
  const qs = query(filter);
  const tasks = useQuery({
    queryKey: taskKeys.list(org, id, qs),
    queryFn: () => api<Task[]>('GET', `${projectPath(org, id)}/tasks${qs ? `?${qs}` : ''}`),
  });

  if (wedding.isPending) return <Spinner />;
  if (!wedding.data) return <FormMessage>{errorMessage(wedding.error, t)}</FormMessage>;
  const can = (perm: string) => wedding.data.permissions.includes(perm);
  const canEdit = can('tasks:write');

  const groups = [
    ...(milestones.data ?? []).map((m) => ({
      id: m.id,
      title: m.title,
      due: m.due_date,
      tasks: (tasks.data ?? []).filter((task) => task.milestone_id === m.id),
    })),
    {
      id: 'none',
      title: t('tasks.noMilestone'),
      due: null,
      tasks: (tasks.data ?? []).filter((task) => !task.milestone_id),
    },
  ].filter((g) => g.tasks.length > 0);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={
          <>
            <Link to="/app/weddings">{t('weddings.title')}</Link> /{' '}
            <Link to={`/app/weddings/${id}`}>{wedding.data.title}</Link>
          </>
        }
        title={wedding.data.title}
      />
      <WeddingNav id={id} />

      <div role="group" aria-label={t('tasks.filter')} className="flex flex-wrap gap-2">
        {FILTERS.map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={filter === option}
            onClick={() => setFilter(option)}
            className={cn(
              'h-9 rounded-full border px-4 text-sm',
              filter === option
                ? 'border-accent bg-accent-soft font-semibold text-ink'
                : 'border-line bg-surface text-ink-soft',
            )}
          >
            {t(`tasks.filters.${option}`)}
          </button>
        ))}
      </div>

      {canEdit && <NewTaskForm org={org} projectId={id} milestones={milestones.data ?? []} />}

      {tasks.isPending ? (
        <Spinner />
      ) : groups.length === 0 ? (
        <Card>
          <p className="text-sm text-muted">{t('tasks.empty')}</p>
        </Card>
      ) : (
        groups.map((group) => (
          <Card key={group.id} className="flex flex-col gap-1 py-4">
            <h2 className="font-display text-[22px] font-semibold">
              {group.title}{' '}
              {group.due && (
                <span className="font-sans text-xs font-normal text-muted">
                  · {t('tasks.dueBy', { date: formatDate(group.due) })}
                </span>
              )}
            </h2>
            <ul>
              {group.tasks.map((task) => (
                <TaskRow
                  key={task.id}
                  org={org}
                  task={task}
                  canEdit={canEdit}
                  onOpen={(t) => setOpenTask(t.id)}
                />
              ))}
            </ul>
          </Card>
        ))
      )}

      {canEdit && <NewMilestoneForm org={org} projectId={id} />}
      <p className="text-sm text-muted">{t('tasks.visibilityHint')}</p>

      {openTask && (
        <TaskDialog
          org={org}
          projectId={id}
          taskId={openTask}
          milestones={milestones.data ?? []}
          team={wedding.data.team}
          canEdit={canEdit}
          canComment={can('comments:write')}
          onClose={() => setOpenTask(null)}
        />
      )}
    </div>
  );
}

function NewTaskForm({
  org,
  projectId,
  milestones,
}: {
  org: string;
  projectId: string;
  milestones: Milestone[];
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState('');
  const [milestone, setMilestone] = useState('');
  const [due, setDue] = useState('');
  const add = useMutation({
    mutationFn: () =>
      api('POST', `${projectPath(org, projectId)}/tasks`, {
        title,
        milestone_id: milestone || null,
        due_date: due || null,
      }),
    onSuccess: async () => {
      setTitle('');
      setDue('');
      await queryClient.invalidateQueries({ queryKey: ['org', org] });
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    add.mutate();
  }

  return (
    <Card className="py-4">
      <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-2">
        <Input
          aria-label={t('tasks.newTask')}
          placeholder={t('tasks.newTask')}
          className="min-w-0 flex-[3_1_220px]"
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <Select
          aria-label={t('tasks.fields.milestone')}
          className="min-w-0 flex-[2_1_180px]"
          value={milestone}
          onChange={(e) => setMilestone(e.target.value)}
        >
          <option value="">{t('tasks.noMilestone')}</option>
          {milestones.map((m) => (
            <option key={m.id} value={m.id}>
              {m.title}
            </option>
          ))}
        </Select>
        <Input
          aria-label={t('tasks.fields.dueDate')}
          type="date"
          className="flex-[1_1_150px]"
          value={due}
          onChange={(e) => setDue(e.target.value)}
        />
        <Button type="submit" className="h-11" disabled={add.isPending}>
          {t('tasks.addTask')}
        </Button>
      </form>
      {add.isError && (
        <div className="pt-3">
          <FormMessage>{errorMessage(add.error, t)}</FormMessage>
        </div>
      )}
    </Card>
  );
}

function NewMilestoneForm({ org, projectId }: { org: string; projectId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState('');
  const [due, setDue] = useState('');
  const add = useMutation({
    mutationFn: () =>
      api('POST', `${projectPath(org, projectId)}/milestones`, {
        title,
        due_date: due || null,
      }),
    onSuccess: async () => {
      setTitle('');
      setDue('');
      await queryClient.invalidateQueries({ queryKey: ['org', org] });
    },
  });
  return (
    <Card className="flex flex-col gap-3 py-4">
      <h2 className="font-display text-[22px] font-semibold">{t('tasks.addMilestone')}</h2>
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate();
        }}
      >
        <Input
          aria-label={t('tasks.milestoneTitle')}
          placeholder={t('tasks.milestoneTitle')}
          className="min-w-0 flex-[3_1_220px]"
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <Input
          aria-label={t('tasks.milestoneDue')}
          type="date"
          className="flex-[1_1_150px]"
          value={due}
          onChange={(e) => setDue(e.target.value)}
        />
        <Button type="submit" variant="secondary" className="h-11" disabled={add.isPending}>
          {t('common.add')}
        </Button>
      </form>
    </Card>
  );
}
