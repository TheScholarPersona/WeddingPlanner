import { api, type Schemas } from '@/lib/api/client';

export type WeddingSummary = Schemas['ProjectSummaryOut'];
export type Wedding = Schemas['ProjectDetailOut'];
export type WeddingVendor = Schemas['ProjectVendorOut'];
export type Dashboard = Schemas['DashboardOut'];
export type Template = Schemas['TemplateOut'];
export type Client = Schemas['ClientOut'];
export type Vendor = Schemas['VendorOut'];
export type Member = Schemas['MemberOut'];

export const keys = {
  dashboard: (org: string) => ['org', org, 'dashboard'] as const,
  weddings: (org: string, params: string) => ['org', org, 'weddings', params] as const,
  wedding: (org: string, id: string) => ['org', org, 'wedding', id] as const,
  weddingVendors: (org: string, id: string) => ['org', org, 'wedding', id, 'vendors'] as const,
  clients: (org: string, params = '') => ['org', org, 'clients', params] as const,
  client: (org: string, id: string) => ['org', org, 'client', id] as const,
  vendors: (org: string) => ['org', org, 'vendors'] as const,
  templates: (org: string) => ['org', org, 'templates'] as const,
  template: (org: string, id: string) => ['org', org, 'template', id] as const,
  members: (org: string) => ['org', org, 'members'] as const,
};

export const weddingPath = (org: string, id: string) => `/orgs/${org}/projects/${id}`;

export function updateWedding(org: string, wedding: Wedding, body: Record<string, unknown>) {
  return api<Wedding>('PATCH', weddingPath(org, wedding.id), body, {
    'If-Match': `"${wedding.version}"`,
  });
}
