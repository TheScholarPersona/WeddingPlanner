import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { api } from '@/lib/api/client';
import { formatDate } from '@/lib/format';
import { cn } from '@/lib/utils';

import { portalPath, type PortalTask } from './api';

export function PortalTaskItem({
  projectId,
  task,
  showChecklist = false,
}: {
  projectId: string;
  task: PortalTask;
  showChecklist?: boolean;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const done = task.status === 'done';
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['portal', projectId] });
  const toggle = useMutation({
    mutationFn: (complete: boolean) =>
      api('POST', `${portalPath(projectId)}/tasks/${task.id}/${complete ? 'complete' : 'reopen'}`),
    onSettled: refresh,
  });
  const tick = useMutation({
    mutationFn: ({ item, isDone }: { item: string; isDone: boolean }) =>
      api('PATCH', `${portalPath(projectId)}/tasks/${task.id}/checklist/${item}`, {
        is_done: isDone,
      }),
    onSettled: refresh,
  });
  const meta = [
    task.due_date ? t('portal.due', { date: formatDate(task.due_date) }) : null,
    task.checklist.length
      ? t('portal.checklist', {
          done: task.checklist.filter((i) => i.is_done).length,
          total: task.checklist.length,
        })
      : null,
    !task.for_couple ? t('portal.byPlanner') : null,
  ].filter(Boolean);

  return (
    <li className="flex flex-col gap-2.5 rounded-xl border border-line bg-surface px-4 py-3.5">
      <div className="flex min-h-11 items-center gap-3">
        <input
          type="checkbox"
          id={`portal-task-${task.id}`}
          aria-label={t('tasks.markDone', { title: task.title })}
          className="size-5 shrink-0 accent-accent"
          checked={toggle.isPending ? toggle.variables : done}
          disabled={!task.for_couple || toggle.isPending}
          onChange={(e) => toggle.mutate(e.target.checked)}
        />
        <span className="flex flex-col gap-0.5">
          <label
            htmlFor={`portal-task-${task.id}`}
            className={cn('text-[15px] font-medium', done && 'text-muted line-through')}
          >
            {task.title}
          </label>
          <span className={cn('text-xs', task.overdue ? 'text-danger' : 'text-muted')}>
            {meta.join(' · ')}
          </span>
        </span>
      </div>
      {showChecklist && task.checklist.length > 0 && (
        <ul className="flex flex-col gap-2 pl-8">
          {task.checklist.map((item) => (
            <li key={item.id}>
              <label className="flex items-center gap-2.5 text-sm">
                <input
                  type="checkbox"
                  className="size-[18px] accent-accent"
                  checked={item.is_done}
                  disabled={!task.for_couple}
                  onChange={(e) => tick.mutate({ item: item.id, isDone: e.target.checked })}
                />
                <span className={item.is_done ? 'text-muted line-through' : ''}>{item.title}</span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
