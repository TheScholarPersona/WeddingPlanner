import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { Dialog } from '@/components/Dialog';
import { Field } from '@/components/Field';
import { FormMessage } from '@/components/FormMessage';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { api } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';

import { projectPath, taskKeys, type Comment, type Milestone, type TaskDetail } from './api';
import { TaskCheckbox } from './TaskCheckbox';

export interface TeamMember {
  membership_id: string;
  full_name: string;
}

interface Props {
  org: string;
  projectId: string;
  taskId: string;
  milestones: Milestone[];
  team: TeamMember[];
  canEdit: boolean;
  canComment: boolean;
  onClose: () => void;
}

export function TaskDialog(props: Props) {
  const { t } = useTranslation();
  const { org, projectId, taskId, onClose } = props;
  const task = useQuery({
    queryKey: taskKeys.detail(org, projectId, taskId),
    queryFn: () => api<TaskDetail>('GET', `${projectPath(org, projectId)}/tasks/${taskId}`),
  });

  return (
    <Dialog title={task.data?.title ?? t('tasks.task')} onClose={onClose}>
      <div className="flex max-h-[75vh] flex-col gap-6 overflow-y-auto pr-1">
        {task.data ? (
          <TaskBody {...props} task={task.data} />
        ) : task.isError ? (
          <FormMessage>{errorMessage(task.error, t)}</FormMessage>
        ) : (
          <Spinner />
        )}
      </div>
    </Dialog>
  );
}

function TaskBody({ task, ...props }: Props & { task: TaskDetail }) {
  const { t } = useTranslation();
  return (
    <>
      <div className="flex items-center gap-3 text-sm">
        <TaskCheckbox org={props.org} task={task} disabled={!props.canEdit} />
        <span>
          {task.status === 'done' && task.completed_by_name
            ? t('tasks.doneBy', { name: task.completed_by_name })
            : null}
        </span>
      </div>
      <TaskForm key={task.id} task={task} {...props} />
      <Checklist task={task} {...props} />
      <Comments task={task} {...props} />
    </>
  );
}

function TaskForm({
  org,
  projectId,
  task,
  milestones,
  team,
  canEdit,
  onClose,
}: Props & { task: TaskDetail }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    title: task.title,
    description: task.description ?? '',
    milestone_id: task.milestone_id ?? '',
    due_date: task.due_date ?? '',
    priority: task.priority,
    assignee: task.assignee_type === 'client' ? 'client' : (task.assignee_membership_id ?? ''),
    visibility: task.visibility,
  });
  const set = (key: keyof typeof form) => (value: string) =>
    setForm((current) => ({ ...current, [key]: value }));
  const path = `${projectPath(org, projectId)}/tasks/${task.id}`;
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['org', org] });

  const save = useMutation({
    mutationFn: () =>
      api<TaskDetail>(
        'PATCH',
        path,
        {
          title: form.title,
          description: form.description || null,
          milestone_id: form.milestone_id || null,
          due_date: form.due_date || null,
          priority: form.priority,
          assignee_type: form.assignee === 'client' ? 'client' : 'team',
          assignee_membership_id:
            form.assignee && form.assignee !== 'client' ? form.assignee : null,
          visibility: form.visibility,
        },
        { 'If-Match': `"${task.version}"` },
      ),
    onSuccess: async (updated) => {
      queryClient.setQueryData(taskKeys.detail(org, projectId, task.id), updated);
      await refresh();
    },
  });
  const remove = useMutation({
    mutationFn: () => api('DELETE', path),
    onSuccess: async () => {
      await refresh();
      onClose();
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate();
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <fieldset disabled={!canEdit} className="grid gap-4 sm:grid-cols-2">
        <Field id="task-title" label={t('tasks.fields.title')} className="sm:col-span-2">
          <Input
            id="task-title"
            required
            value={form.title}
            onChange={(e) => set('title')(e.target.value)}
          />
        </Field>
        <Field
          id="task-description"
          label={t('tasks.fields.description')}
          className="sm:col-span-2"
        >
          <Textarea
            id="task-description"
            value={form.description}
            onChange={(e) => set('description')(e.target.value)}
          />
        </Field>
        <Field id="task-milestone" label={t('tasks.fields.milestone')}>
          <Select
            id="task-milestone"
            value={form.milestone_id}
            onChange={(e) => set('milestone_id')(e.target.value)}
          >
            <option value="">{t('tasks.noMilestone')}</option>
            {milestones.map((m) => (
              <option key={m.id} value={m.id}>
                {m.title}
              </option>
            ))}
          </Select>
        </Field>
        <Field id="task-due" label={t('tasks.fields.dueDate')}>
          <Input
            id="task-due"
            type="date"
            value={form.due_date}
            onChange={(e) => set('due_date')(e.target.value)}
          />
        </Field>
        <Field id="task-assignee" label={t('tasks.fields.assignee')}>
          <Select
            id="task-assignee"
            value={form.assignee}
            onChange={(e) => set('assignee')(e.target.value)}
          >
            <option value="">{t('tasks.unassigned')}</option>
            <option value="client">{t('tasks.couple')}</option>
            {team.map((m) => (
              <option key={m.membership_id} value={m.membership_id}>
                {m.full_name}
              </option>
            ))}
          </Select>
        </Field>
        <Field id="task-priority" label={t('tasks.fields.priority')}>
          <Select
            id="task-priority"
            value={form.priority}
            onChange={(e) => set('priority')(e.target.value)}
          >
            {(['low', 'normal', 'high'] as const).map((p) => (
              <option key={p} value={p}>
                {t(`tasks.priority.${p}`)}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          id="task-visibility"
          label={t('tasks.fields.visibility')}
          hint={t('tasks.visibilityHint')}
          className="sm:col-span-2"
        >
          <Select
            id="task-visibility"
            value={form.visibility}
            onChange={(e) => set('visibility')(e.target.value)}
          >
            <option value="internal">{t('tasks.internal')}</option>
            <option value="client">{t('tasks.shared')}</option>
          </Select>
        </Field>
      </fieldset>
      {(save.isError || remove.isError) && (
        <FormMessage>{errorMessage(save.error ?? remove.error, t)}</FormMessage>
      )}
      {save.isSuccess && <FormMessage tone="success">{t('settings.saved')}</FormMessage>}
      {canEdit && (
        <div className="flex flex-wrap justify-between gap-3">
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              if (window.confirm(t('tasks.confirmDelete', { title: task.title }))) remove.mutate();
            }}
          >
            {t('common.delete')}
          </Button>
          <Button type="submit" disabled={save.isPending}>
            {t('common.save')}
          </Button>
        </div>
      )}
    </form>
  );
}

function Checklist({ org, projectId, task, canEdit }: Props & { task: TaskDetail }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState('');
  const base = `${projectPath(org, projectId)}/tasks/${task.id}/checklist`;
  const update = (data: TaskDetail) => {
    queryClient.setQueryData(taskKeys.detail(org, projectId, task.id), data);
    void queryClient.invalidateQueries({ queryKey: taskKeys.all(org, projectId) });
  };
  const add = useMutation({
    mutationFn: () => api<TaskDetail>('POST', base, { title }),
    onSuccess: (data) => {
      setTitle('');
      update(data);
    },
  });
  const toggle = useMutation({
    mutationFn: ({ id, done }: { id: string; done: boolean }) =>
      api<TaskDetail>('PATCH', `${base}/${id}`, { is_done: done }),
    onSuccess: update,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api<TaskDetail>('DELETE', `${base}/${id}`),
    onSuccess: update,
  });

  if (!canEdit && task.checklist.length === 0) return null;
  return (
    <section className="flex flex-col gap-2 border-t border-line pt-4">
      <h3 className="text-sm font-semibold">
        {t('tasks.checklist')}{' '}
        {task.checklist_total > 0 && (
          <span className="font-normal text-muted">
            {t('tasks.checklistCount', {
              done: task.checklist_done,
              total: task.checklist_total,
            })}
          </span>
        )}
      </h3>
      <ul className="flex flex-col gap-1">
        {task.checklist.map((item) => (
          <li key={item.id} className="flex items-center justify-between gap-2 text-sm">
            <label className="flex items-center gap-2.5">
              <input
                type="checkbox"
                className="size-4 accent-accent"
                checked={item.is_done}
                disabled={!canEdit}
                onChange={(e) => toggle.mutate({ id: item.id, done: e.target.checked })}
              />
              <span className={item.is_done ? 'text-muted line-through' : ''}>{item.title}</span>
            </label>
            {canEdit && (
              <Button
                variant="ghost"
                size="sm"
                aria-label={t('templates.removeItem', { title: item.title })}
                onClick={() => remove.mutate(item.id)}
              >
                {t('common.remove')}
              </Button>
            )}
          </li>
        ))}
      </ul>
      {canEdit && (
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          <Input
            aria-label={t('tasks.newChecklistItem')}
            placeholder={t('tasks.newChecklistItem')}
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <Button type="submit" size="sm" className="h-11" disabled={add.isPending}>
            {t('common.add')}
          </Button>
        </form>
      )}
    </section>
  );
}

function Comments({ org, projectId, task, canComment }: Props & { task: TaskDetail }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [body, setBody] = useState('');
  const key = taskKeys.comments(org, projectId, task.id);
  const comments = useQuery({
    queryKey: key,
    queryFn: () =>
      api<Comment[]>(
        'GET',
        `${projectPath(org, projectId)}/comments?target_type=task&target_id=${task.id}`,
      ),
  });
  const add = useMutation({
    mutationFn: () =>
      api<Comment>('POST', `${projectPath(org, projectId)}/comments`, {
        target_type: 'task',
        target_id: task.id,
        body,
      }),
    onSuccess: async () => {
      setBody('');
      await queryClient.invalidateQueries({ queryKey: key });
      await queryClient.invalidateQueries({ queryKey: taskKeys.all(org, projectId) });
    },
  });

  return (
    <section className="flex flex-col gap-3 border-t border-line pt-4">
      <h3 className="text-sm font-semibold">{t('tasks.commentsTitle')}</h3>
      {comments.data?.length === 0 && <p className="text-sm text-muted">{t('tasks.noComments')}</p>}
      <ul className="flex flex-col gap-3">
        {comments.data?.map((comment) => (
          <li key={comment.id} className="rounded-lg bg-subtle px-3 py-2 text-sm">
            <div className="text-xs text-muted">
              <span className="font-semibold text-ink-soft">{comment.author_name}</span> ·{' '}
              {new Intl.DateTimeFormat('de-DE', { dateStyle: 'short', timeStyle: 'short' }).format(
                new Date(comment.created_at),
              )}
              {comment.edited_at && ` · ${t('tasks.edited')}`}
            </div>
            <p className="whitespace-pre-line">{comment.body}</p>
          </li>
        ))}
      </ul>
      {canComment && (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          <Textarea
            aria-label={t('tasks.writeComment')}
            placeholder={t('tasks.writeComment')}
            className="min-h-16"
            required
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <div>
            <Button type="submit" size="sm" disabled={add.isPending}>
              {t('tasks.postComment')}
            </Button>
          </div>
          {add.isError && <FormMessage>{errorMessage(add.error, t)}</FormMessage>}
        </form>
      )}
    </section>
  );
}
