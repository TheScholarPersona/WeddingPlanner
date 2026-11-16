import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, upload } from '@/lib/api/client';

import {
  fromTeam,
  fromTeamSummary,
  type Board,
  type BoardSummary,
  type MoodboardScope,
} from './api';

/* eslint-disable @typescript-eslint/no-explicit-any -- planner and portal shapes differ */
function toBoard(scope: MoodboardScope, data: any): Board {
  return scope.kind === 'team' ? fromTeam(data) : (data as Board);
}

export function useBoards(scope: MoodboardScope) {
  return useQuery({
    queryKey: scope.key,
    queryFn: async () => {
      const data = await api<any[]>('GET', scope.base);
      return data.map((b): BoardSummary => (scope.kind === 'team' ? fromTeamSummary(b) : b));
    },
  });
}

export function useBoard(scope: MoodboardScope, id: string) {
  return useQuery({
    queryKey: [...scope.key, id],
    queryFn: async () => toBoard(scope, await api<any>('GET', `${scope.base}/${id}`)),
    // Images are processed after upload (virus scan, previews): check again until ready.
    refetchInterval: (query) =>
      query.state.data?.items.some((i) => !i.ready && i.scan_status !== 'infected') ? 2500 : false,
  });
}

/** A change to a board; the API answers with the whole board, which replaces the cache. */
export function useBoardMutation<V>(
  scope: MoodboardScope,
  boardId: string,
  request: (vars: V) => Promise<unknown>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (vars: V) => request(vars),
    onSuccess: (data) => {
      if (data && typeof data === 'object' && 'items' in data) {
        queryClient.setQueryData([...scope.key, boardId], toBoard(scope, data));
      }
      void queryClient.invalidateQueries({ queryKey: scope.key, exact: true });
    },
  });
}

export function uploadImages(
  scope: MoodboardScope,
  boardId: string,
  files: File[],
  sectionId: string | null,
) {
  const form = new FormData();
  for (const file of files) form.append('files', file);
  if (sectionId) form.append('section_id', sectionId);
  return upload<any>(`${scope.base}/${boardId}/items`, form);
}
/* eslint-enable @typescript-eslint/no-explicit-any */
