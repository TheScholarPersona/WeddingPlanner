import type { Schemas } from '@/lib/api/client';

export type Item = Schemas['ItemOut'];
export type Section = Schemas['SectionOut'];
export type Comment = Schemas['CommentOut'];

/** The fields planner and portal boards share; the planner's has a few more. */
export interface Board {
  id: string;
  title: string;
  palette: string[];
  item_count: number;
  selected_count: number;
  preview: string[];
  updated_at: string;
  version: number;
  sections: Section[];
  items: Item[];
  can_manage: boolean;
  can_delete: boolean;
  from_couple: boolean;
  /** Planner only */
  visibility?: 'internal' | 'client';
  notes_internal?: string | null;
}

export interface BoardSummary {
  id: string;
  title: string;
  palette: string[];
  item_count: number;
  selected_count: number;
  preview: string[];
  updated_at: string;
  from_couple: boolean;
  visibility?: 'internal' | 'client';
}

type TeamBoard = Schemas['BoardOut'];
type TeamSummary = Schemas['BoardSummaryOut'];

export function fromTeam(board: TeamBoard): Board {
  return { ...board, from_couple: board.created_by_type === 'client' };
}

export function fromTeamSummary(board: TeamSummary): BoardSummary {
  return { ...board, from_couple: board.created_by_type === 'client' };
}

export type Size = 'thumb' | 'display' | 'original';

/**
 * Where a moodboard lives. Planner and portal call the same operations under different
 * paths; the portal never gets originals, exports or the comment visibility switch.
 */
export interface MoodboardScope {
  kind: 'team' | 'couple';
  key: readonly unknown[];
  base: string;
  /** Link to a board page inside the app. */
  boardLink: (boardId: string) => string;
  listLink: string;
  commentsPath: (boardId: string, itemId: string) => string;
  /** Planner: comments are created through the wedding's comment endpoint. */
  commentPost: (boardId: string, itemId: string) => string;
}

export function teamScope(org: string, project: string): MoodboardScope {
  const base = `/orgs/${org}/projects/${project}/moodboards`;
  return {
    kind: 'team',
    key: ['org', org, 'wedding', project, 'moodboards'],
    base,
    boardLink: (id) => `/app/weddings/${project}/moodboards/${id}`,
    listLink: `/app/weddings/${project}/moodboards`,
    commentsPath: (_b, item) =>
      `/orgs/${org}/projects/${project}/comments?target_type=moodboard_item&target_id=${item}`,
    commentPost: () => `/orgs/${org}/projects/${project}/comments`,
  };
}

export function coupleScope(project: string): MoodboardScope {
  const base = `/portal/projects/${project}/moodboards`;
  return {
    kind: 'couple',
    key: ['portal', project, 'moodboards'],
    base,
    boardLink: (id) => `/portal/inspiration/${id}`,
    listLink: '/portal/inspiration',
    commentsPath: (board, item) => `${base}/${board}/items/${item}/comments`,
    commentPost: (board, item) => `${base}/${board}/items/${item}/comments`,
  };
}

export const imageUrl = (scope: MoodboardScope, board: string, item: string, size: Size) =>
  `/api/v1${scope.base}/${board}/items/${item}/image?size=${size}`;

export const ACCEPT_IMAGES = '.jpg,.jpeg,.png,.webp,.heic,.heif,image/*';
export const MAX_IMAGE_MB = 15;
export const MAX_FILES = 20;
