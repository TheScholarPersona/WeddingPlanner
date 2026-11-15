import { useQuery } from '@tanstack/react-query';

import { api, type Schemas } from '@/lib/api/client';

export type PortalProject = Schemas['PortalProjectSummary'];
export type PortalOverview = Schemas['PortalOverview'];
export type PortalTask = Schemas['PortalTask'];
export type PortalBudget = Schemas['PortalBudget'];

export const portalKeys = {
  projects: ['portal', 'projects'] as const,
  overview: (id: string) => ['portal', id, 'overview'] as const,
  tasks: (id: string) => ['portal', id, 'tasks'] as const,
  budget: (id: string) => ['portal', id, 'budget'] as const,
};

export const portalPath = (id: string) => `/portal/projects/${id}`;

/** The couple's wedding. Couples normally have exactly one; the first is shown. */
export function usePortalProject() {
  const projects = useQuery({
    queryKey: portalKeys.projects,
    queryFn: () => api<PortalProject[]>('GET', '/portal/projects'),
  });
  return { project: projects.data?.[0], isPending: projects.isPending, error: projects.error };
}

/** Readable text color (ink or white) on a given hex background. */
export function textOn(hex: string): string {
  const value = hex.replace('#', '');
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(value.slice(i, i + 2), 16) / 255);
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const luminance = 0.2126 * lin(r!) + 0.7152 * lin(g!) + 0.0722 * lin(b!);
  return luminance > 0.35 ? '#1f1d1a' : '#ffffff';
}
