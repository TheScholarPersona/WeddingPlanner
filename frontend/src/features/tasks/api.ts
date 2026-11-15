import { api, type Schemas } from '@/lib/api/client';

export type Task = Schemas['TaskOut'];
export type TaskDetail = Schemas['TaskDetailOut'];
export type MyTask = Schemas['MyTaskOut'];
export type Milestone = Schemas['MilestoneDetailOut'];
export type Comment = Schemas['CommentOut'];
export type ActivityPage = Schemas['ActivityPageOut'];

export const projectPath = (org: string, project: string) => `/orgs/${org}/projects/${project}`;

export const taskKeys = {
  all: (org: string, project: string) => ['org', org, 'wedding', project, 'tasks'] as const,
  list: (org: string, project: string, filter: string) =>
    ['org', org, 'wedding', project, 'tasks', 'list', filter] as const,
  detail: (org: string, project: string, task: string) =>
    ['org', org, 'wedding', project, 'tasks', 'detail', task] as const,
  milestones: (org: string, project: string) =>
    ['org', org, 'wedding', project, 'tasks', 'milestones'] as const,
  comments: (org: string, project: string, task: string) =>
    ['org', org, 'wedding', project, 'tasks', 'comments', task] as const,
  activity: (org: string, project: string) => ['org', org, 'wedding', project, 'activity'] as const,
  mine: (org: string, status: string) => ['org', org, 'my-tasks', status] as const,
};

export function setTaskDone(org: string, task: Pick<Task, 'id' | 'project_id'>, done: boolean) {
  return api<TaskDetail>(
    'POST',
    `${projectPath(org, task.project_id)}/tasks/${task.id}/${done ? 'complete' : 'reopen'}`,
  );
}
