import type { Schemas } from '@/lib/api/client';

export type Document = Schemas['DocumentOut'];
export type DocumentDetail = Schemas['DocumentDetailOut'];
export type DocumentVersion = Schemas['VersionOut'];

export const CATEGORIES = [
  'contract',
  'quote',
  'invoice',
  'planning',
  'inspiration',
  'other',
] as const;
export type Category = (typeof CATEGORIES)[number];

/** File types the server accepts (it checks the content too). */
export const ACCEPT = '.pdf,.png,.jpg,.jpeg,.gif,.webp,.heic,.docx,.xlsx,.pptx,.doc,.xls,.txt,.csv';
export const MAX_UPLOAD_MB = 25;

export const documentKeys = {
  list: (org: string, project: string) => ['org', org, 'wedding', project, 'documents'] as const,
};

export const documentsPath = (org: string, project: string) =>
  `/orgs/${org}/projects/${project}/documents`;
