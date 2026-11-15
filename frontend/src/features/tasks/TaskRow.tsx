import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/Badge';
import { formatDate } from '@/lib/format';
import { cn } from '@/lib/utils';

import type { Task } from './api';
import { TaskCheckbox } from './TaskCheckbox';

export function TaskRow({
  org,
  task,
  canEdit,
  onOpen,
  subtitle,
}: {
  org: string;
  task: Task;
  canEdit: boolean;
  onOpen: (task: Task) => void;
  subtitle?: string;
}) {
  const { t } = useTranslation();
  const done = task.status === 'done';
  const meta = [
    subtitle,
    task.checklist_total
      ? t('tasks.checklistProgress', { done: task.checklist_done, total: task.checklist_total })
      : null,
    task.comment_count ? t('tasks.comments', { count: task.comment_count }) : null,
  ].filter(Boolean);

  return (
    <li className="grid grid-cols-[28px_minmax(0,1fr)] items-center gap-x-3 gap-y-1 border-t border-line-soft px-1 py-3 text-sm sm:grid-cols-[28px_minmax(0,1fr)_140px_110px_150px]">
      <TaskCheckbox org={org} task={task} disabled={!canEdit} />
      <button
        type="button"
        onClick={() => onOpen(task)}
        className="flex min-w-0 cursor-pointer flex-col items-start gap-0.5 text-left"
      >
        <span className={cn('font-medium', done && 'text-muted line-through')}>{task.title}</span>
        {meta.length > 0 && <span className="text-xs text-muted">{meta.join(' · ')}</span>}
      </button>
      <span className="col-start-2 text-ink-soft sm:col-start-auto">
        {task.assignee_type === 'client'
          ? t('tasks.couple')
          : (task.assignee_name ?? t('tasks.unassigned'))}
      </span>
      <span
        className={cn(
          'col-start-2 sm:col-start-auto',
          task.overdue ? 'font-semibold text-danger' : 'text-muted',
        )}
      >
        {task.due_date ? formatDate(task.due_date) : t('tasks.noDueDate')}
        {task.overdue && <span className="sr-only"> ({t('tasks.overdue')})</span>}
      </span>
      <span className="col-start-2 sm:col-start-auto">
        <Badge tone={task.visibility === 'client' ? 'accent' : 'neutral'}>
          {task.visibility === 'client' ? t('tasks.shared') : t('tasks.internal')}
        </Badge>
      </span>
    </li>
  );
}
