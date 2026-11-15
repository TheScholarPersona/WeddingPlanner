import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { EmptyState } from '@/components/EmptyState';
import { PageHeader } from '@/components/PageHeader';
import { Spinner } from '@/components/Spinner';
import { Card } from '@/components/ui/card';
import { useActiveOrg } from '@/features/auth/useActiveOrg';
import { api } from '@/lib/api/client';
import { formatDate } from '@/lib/format';
import { cn } from '@/lib/utils';

import { taskKeys, type MyTask } from './api';
import { TaskCheckbox } from './TaskCheckbox';

type Bucket = 'overdue' | 'thisWeek' | 'later' | 'done';

function bucket(task: MyTask, today: string, weekEnd: string): Bucket {
  if (!task.due_date) return 'later';
  if (task.due_date < today) return 'overdue';
  if (task.due_date <= weekEnd) return 'thisWeek';
  return 'later';
}

export function MyTasksPage() {
  const { t } = useTranslation();
  const { membership } = useActiveOrg();
  const org = membership.organization_id;
  const [status, setStatus] = useState<'open' | 'done'>('open');
  const tasks = useQuery({
    queryKey: taskKeys.mine(org, status),
    queryFn: () => api<MyTask[]>('GET', `/orgs/${org}/tasks?status=${status}`),
  });

  const now = new Date();
  const today = now.toISOString().slice(0, 10);
  const weekEnd = new Date(now.getTime() + 7 * 86_400_000).toISOString().slice(0, 10);
  const order: Bucket[] = status === 'open' ? ['overdue', 'thisWeek', 'later'] : ['done'];
  const grouped = (tasks.data ?? []).reduce<Partial<Record<Bucket, MyTask[]>>>((acc, task) => {
    const key: Bucket = status === 'open' ? bucket(task, today, weekEnd) : 'done';
    (acc[key] ??= []).push(task);
    return acc;
  }, {});

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t('tasks.myTitle')} subtitle={t('tasks.mySubtitle')} />
      <div role="group" aria-label={t('tasks.filter')} className="flex gap-2">
        {(['open', 'done'] as const).map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={status === option}
            onClick={() => setStatus(option)}
            className={cn(
              'h-9 rounded-full border px-4 text-sm',
              status === option
                ? 'border-accent bg-accent-soft font-semibold text-ink'
                : 'border-line bg-surface text-ink-soft',
            )}
          >
            {t(`tasks.filters.${option}`)}
          </button>
        ))}
      </div>
      {tasks.isPending ? (
        <Spinner />
      ) : !tasks.data?.length ? (
        <EmptyState title={t('tasks.myEmptyTitle')} body={t('tasks.myEmptyBody')} />
      ) : (
        order
          .filter((key) => grouped[key]?.length)
          .map((key) => (
            <Card key={key} className="flex flex-col gap-1 py-4">
              <h2
                className={cn(
                  'font-display text-[22px] font-semibold',
                  key === 'overdue' && 'text-danger',
                )}
              >
                {t(`tasks.buckets.${key}`)}
              </h2>
              <ul>
                {grouped[key]!.map((task) => (
                  <li
                    key={task.id}
                    className="grid grid-cols-[28px_minmax(0,1fr)_auto] items-center gap-3 border-t border-line-soft py-3 text-sm"
                  >
                    <TaskCheckbox org={org} task={task} />
                    <span className="flex min-w-0 flex-col">
                      <span
                        className={cn(
                          'font-medium',
                          task.status === 'done' && 'text-muted line-through',
                        )}
                      >
                        {task.title}
                      </span>
                      <Link
                        to={`/app/weddings/${task.project_id}/tasks`}
                        className="text-xs text-accent"
                      >
                        {task.project_title}
                      </Link>
                    </span>
                    <span className={cn('text-right', task.overdue ? 'text-danger' : 'text-muted')}>
                      {task.due_date ? formatDate(task.due_date) : t('tasks.noDueDate')}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          ))
      )}
    </div>
  );
}
