import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { FormMessage } from '@/components/FormMessage';
import { Spinner } from '@/components/Spinner';
import { api } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { formatDate } from '@/lib/format';
import { cn } from '@/lib/utils';

import { portalKeys, portalPath, usePortalProject, type PortalTask } from './api';
import { PortalTaskItem } from './PortalTaskItem';

export function PortalTasksPage() {
  const { t } = useTranslation();
  const { project, isPending } = usePortalProject();
  const [view, setView] = useState<'todo' | 'done'>('todo');
  const tasks = useQuery({
    queryKey: portalKeys.tasks(project?.id ?? ''),
    queryFn: () => api<PortalTask[]>('GET', `${portalPath(project!.id)}/tasks`),
    enabled: !!project,
  });

  if (isPending || tasks.isPending) return <Spinner />;
  if (!project || !tasks.data) return <FormMessage>{errorMessage(tasks.error, t)}</FormMessage>;

  const mine = tasks.data.filter((task) => task.for_couple);
  const todo = tasks.data.filter((task) => task.status !== 'done');
  const shown = view === 'todo' ? todo : tasks.data.filter((task) => task.status === 'done');
  const groups = new Map<string, { title: string; due: string | null; tasks: PortalTask[] }>();
  for (const task of shown) {
    const key = task.milestone_id ?? 'none';
    if (!groups.has(key)) {
      groups.set(key, {
        title: task.milestone_title ?? t('portal.tasks.other'),
        due: null,
        tasks: [],
      });
    }
    groups.get(key)!.tasks.push(task);
  }

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-1">
        <span className="text-sm text-muted">
          {t('portal.tasks.summary', {
            count: mine.length,
            done: mine.filter((task) => task.status === 'done').length,
          })}
        </span>
        <h1 className="font-display text-4xl font-medium">{t('portal.tasks.title')}</h1>
      </header>
      <div
        role="group"
        aria-label={t('tasks.filter')}
        className="grid grid-cols-2 rounded-xl bg-line p-1"
      >
        {(['todo', 'done'] as const).map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={view === option}
            onClick={() => setView(option)}
            className={cn(
              'h-10 rounded-[9px] text-sm',
              view === option ? 'bg-surface font-semibold text-ink' : 'text-ink-soft',
            )}
          >
            {t(`portal.tasks.${option}`, {
              count: option === 'todo' ? todo.length : tasks.data.length - todo.length,
            })}
          </button>
        ))}
      </div>
      {shown.length === 0 && <p className="text-sm text-muted">{t('portal.tasks.empty')}</p>}
      {[...groups.values()].map((group) => (
        <section key={group.title} className="flex flex-col gap-2">
          <h2 className="text-xs font-semibold tracking-wide text-muted uppercase">
            {group.title}
            {group.due && ` · ${formatDate(group.due)}`}
          </h2>
          <ul className="flex flex-col gap-2.5">
            {group.tasks.map((task) => (
              <PortalTaskItem key={task.id} projectId={project.id} task={task} showChecklist />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
