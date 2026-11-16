import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';

import { Badge } from '@/components/Badge';
import { Dialog } from '@/components/Dialog';
import { EmptyState } from '@/components/EmptyState';
import { Field } from '@/components/Field';
import { FormMessage } from '@/components/FormMessage';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { api } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';

import { imageUrl, type BoardSummary, type MoodboardScope } from './api';
import { useBoards } from './hooks';
import { Palette } from './Palette';

export function BoardList({ scope, canCreate }: { scope: MoodboardScope; canCreate: boolean }) {
  const { t } = useTranslation();
  const boards = useBoards(scope);
  const [creating, setCreating] = useState(false);

  if (boards.isPending) return <Spinner />;
  if (!boards.data) return <FormMessage>{errorMessage(boards.error, t)}</FormMessage>;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">
          {scope.kind === 'team' ? t('moodboards.introTeam') : t('moodboards.introCouple')}
        </p>
        {canCreate && <Button onClick={() => setCreating(true)}>{t('moodboards.newBoard')}</Button>}
      </div>
      {boards.data.length === 0 ? (
        <EmptyState
          title={t('moodboards.emptyTitle')}
          body={scope.kind === 'team' ? t('moodboards.emptyTeam') : t('moodboards.emptyCouple')}
        />
      ) : (
        <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {boards.data.map((board) => (
            <li key={board.id}>
              <BoardCard scope={scope} board={board} />
            </li>
          ))}
        </ul>
      )}
      {creating && <NewBoardDialog scope={scope} onClose={() => setCreating(false)} />}
    </div>
  );
}

function BoardCard({ scope, board }: { scope: MoodboardScope; board: BoardSummary }) {
  const { t } = useTranslation();
  const cells = [0, 1, 2, 3];
  return (
    <Link
      to={scope.boardLink(board.id)}
      className="group flex flex-col overflow-hidden rounded-[var(--radius-card)] border border-line bg-surface transition-shadow hover:shadow-md"
    >
      <div className="grid aspect-[4/3] grid-cols-2 grid-rows-2 gap-0.5 bg-subtle">
        {cells.map((i) =>
          board.preview[i] ? (
            <img
              key={i}
              src={imageUrl(scope, board.id, board.preview[i], 'thumb')}
              alt=""
              loading="lazy"
              className="size-full object-cover"
            />
          ) : (
            <div key={i} className="bg-subtle" />
          ),
        )}
      </div>
      <div className="flex flex-col gap-2 p-4">
        <div className="flex items-start justify-between gap-2">
          <span className="font-display text-xl font-semibold group-hover:underline">
            {board.title}
          </span>
          {board.from_couple ? (
            <Badge tone="accent">{t('moodboards.fromCouple')}</Badge>
          ) : (
            board.visibility === 'client' && <Badge tone="accent">{t('moodboards.shared')}</Badge>
          )}
        </div>
        <span className="text-xs text-muted">
          {t('moodboards.counts', { count: board.item_count, selected: board.selected_count })}
        </span>
        {board.palette.length > 0 && <Palette colors={board.palette} size="sm" />}
      </div>
    </Link>
  );
}

function NewBoardDialog({ scope, onClose }: { scope: MoodboardScope; onClose: () => void }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [title, setTitle] = useState('');
  const [template, setTemplate] = useState(true);
  const [shared, setShared] = useState(false);
  const create = useMutation({
    mutationFn: () =>
      api<{ id: string }>('POST', scope.base, {
        title: title.trim(),
        from_template: template,
        visibility: shared ? 'client' : 'internal',
      }),
    onSuccess: async (board) => {
      await queryClient.invalidateQueries({ queryKey: scope.key });
      void navigate(scope.boardLink(board.id));
    },
  });
  return (
    <Dialog title={t('moodboards.newBoard')} onClose={onClose}>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <Field id="board-title" label={t('moodboards.boardTitle')}>
          <Input
            id="board-title"
            required
            maxLength={120}
            placeholder={t('moodboards.titlePlaceholder')}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        <label className="flex items-start gap-2.5 text-sm">
          <input
            type="checkbox"
            className="mt-0.5 size-4 accent-accent"
            checked={template}
            onChange={(e) => setTemplate(e.target.checked)}
          />
          <span>
            {t('moodboards.useTemplate')}
            <span className="block text-xs text-muted">{t('moodboards.templateHint')}</span>
          </span>
        </label>
        {scope.kind === 'team' && (
          <label className="flex items-start gap-2.5 text-sm">
            <input
              type="checkbox"
              className="mt-0.5 size-4 accent-accent"
              checked={shared}
              onChange={(e) => setShared(e.target.checked)}
            />
            <span>
              {t('moodboards.shareWithCouple')}
              <span className="block text-xs text-muted">{t('moodboards.shareHint')}</span>
            </span>
          </label>
        )}
        {create.error && <FormMessage>{errorMessage(create.error, t)}</FormMessage>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={create.isPending}>
            {t('moodboards.create')}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
