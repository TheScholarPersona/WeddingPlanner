import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { setTaskDone, type Task } from './api';

/** Completes or reopens a task; refreshes everything that shows task progress. */
export function TaskCheckbox({
  org,
  task,
  disabled = false,
}: {
  org: string;
  task: Pick<Task, 'id' | 'project_id' | 'title' | 'status'>;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const toggle = useMutation({
    mutationFn: (done: boolean) => setTaskDone(org, task, done),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['org', org] }),
  });
  return (
    <input
      type="checkbox"
      aria-label={t('tasks.markDone', { title: task.title })}
      className="size-[18px] shrink-0 cursor-pointer accent-accent"
      checked={toggle.isPending ? toggle.variables : task.status === 'done'}
      disabled={disabled || toggle.isPending}
      onChange={(e) => toggle.mutate(e.target.checked)}
    />
  );
}
