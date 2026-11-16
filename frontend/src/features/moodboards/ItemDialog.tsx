import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, Heart, X } from 'lucide-react';
import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { FormMessage } from '@/components/FormMessage';
import { Button } from '@/components/ui/button';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { api } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { formatDate } from '@/lib/format';
import { cn } from '@/lib/utils';

import { imageUrl, type Board, type Comment, type Item, type MoodboardScope } from './api';
import { useBoardMutation } from './hooks';

interface Props {
  scope: MoodboardScope;
  board: Board;
  item: Item;
  canSelect: boolean;
  onClose: () => void;
  onNavigate: (direction: 1 | -1) => void;
}

/** Large view of one image: hearts, comments, caption, section and (planner) selection. */
export function ItemDialog({ scope, board, item, canSelect, onClose, onNavigate }: Props) {
  const { t } = useTranslation();
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const path = `${scope.base}/${board.id}/items/${item.id}`;
  const section = board.sections.find((s) => s.id === item.section_id);
  const alt =
    item.caption ||
    t('moodboards.imageIn', { section: section?.title ?? t('moodboards.unsorted') });

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLElement>('button')?.focus();
    const onKey = (event: KeyboardEvent) => {
      const typing = (event.target as HTMLElement).closest('input, textarea, select');
      if (event.key === 'Escape') onClose();
      else if (!typing && event.key === 'ArrowRight') onNavigate(1);
      else if (!typing && event.key === 'ArrowLeft') onNavigate(-1);
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      previous?.focus();
    };
  }, [onClose, onNavigate]);

  const heart = useBoardMutation(scope, board.id, (on: boolean) =>
    api(on ? 'PUT' : 'DELETE', `${path}/heart`),
  );
  const update = useBoardMutation(scope, board.id, (body: Record<string, unknown>) =>
    api('PATCH', path, body),
  );
  const remove = useBoardMutation(scope, board.id, () => api('DELETE', path));

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-center bg-ink/70 p-0 sm:p-6">
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex w-full max-w-6xl flex-col overflow-hidden bg-surface sm:rounded-[var(--radius-card)] lg:flex-row"
      >
        <div className="relative flex min-h-[45vh] flex-1 items-center justify-center bg-ink">
          {item.ready ? (
            <img
              src={imageUrl(scope, board.id, item.id, 'display')}
              alt={alt}
              className="max-h-[80vh] max-w-full object-contain"
            />
          ) : (
            <span className="text-sm text-white/80">{t('moodboards.processing')}</span>
          )}
          <Button
            variant="ghost"
            size="icon"
            aria-label={t('moodboards.previous')}
            className="absolute top-1/2 left-2 -translate-y-1/2 bg-white/80 hover:bg-white"
            onClick={() => onNavigate(-1)}
          >
            <ChevronLeft aria-hidden="true" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label={t('moodboards.next')}
            className="absolute top-1/2 right-2 -translate-y-1/2 bg-white/80 hover:bg-white"
            onClick={() => onNavigate(1)}
          >
            <ChevronRight aria-hidden="true" />
          </Button>
        </div>
        <aside className="flex w-full flex-col gap-4 overflow-y-auto p-5 lg:w-[360px]">
          <div className="flex items-start justify-between gap-2">
            <h2 id={titleId} className="font-display text-2xl font-semibold">
              {item.caption || section?.title || t('moodboards.unsorted')}
            </h2>
            <Button
              variant="ghost"
              size="icon"
              aria-label={t('moodboards.close')}
              onClick={onClose}
            >
              <X aria-hidden="true" />
            </Button>
          </div>
          <p className="text-xs text-muted">
            {[
              item.uploaded_by_type === 'client'
                ? t('moodboards.fromCouple')
                : item.uploaded_by_name,
              formatDate(item.created_at),
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>

          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant={item.hearted_by_me ? 'primary' : 'secondary'}
              size="sm"
              aria-pressed={item.hearted_by_me}
              disabled={heart.isPending}
              onClick={() => heart.mutate(!item.hearted_by_me)}
            >
              <Heart
                aria-hidden="true"
                className={cn('size-4', item.hearted_by_me && 'fill-current')}
              />
              {item.hearted_by_me ? t('moodboards.hearted') : t('moodboards.heart')}
            </Button>
            {item.heart_names.length > 0 && (
              <span className="text-xs text-muted">
                {t('moodboards.heartedBy', { names: item.heart_names.join(', ') })}
              </span>
            )}
          </div>

          {canSelect && (
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-1 text-sm font-medium">{t('moodboards.decision')}</legend>
              <div className="flex flex-wrap gap-2">
                {(['selected', 'proposed', 'discarded'] as const).map((status) => (
                  <Button
                    key={status}
                    size="sm"
                    variant={item.status === status ? 'primary' : 'secondary'}
                    aria-pressed={item.status === status}
                    disabled={update.isPending}
                    onClick={() => update.mutate({ status })}
                  >
                    {t(`moodboards.status.${status}`)}
                  </Button>
                ))}
              </div>
            </fieldset>
          )}
          {!canSelect && item.status === 'selected' && (
            <p className="text-sm font-medium text-accent-strong">{t('moodboards.selectedHint')}</p>
          )}

          {item.can_edit && (
            <EditFields
              key={`${item.caption}-${item.section_id}`}
              board={board}
              item={item}
              busy={update.isPending}
              onSave={(body) => update.mutate(body)}
            />
          )}

          <Comments scope={scope} board={board} item={item} />

          {(update.error || heart.error || remove.error) && (
            <FormMessage>
              {errorMessage(update.error ?? heart.error ?? remove.error, t)}
            </FormMessage>
          )}
          {item.can_edit && (
            <Button
              variant="ghost"
              className="self-start text-danger"
              disabled={remove.isPending}
              onClick={() => {
                if (window.confirm(t('moodboards.confirmDeleteImage'))) {
                  remove.mutate(undefined, { onSuccess: onClose });
                }
              }}
            >
              {t('moodboards.deleteImage')}
            </Button>
          )}
        </aside>
      </div>
    </div>
  );
}

function EditFields({
  board,
  item,
  busy,
  onSave,
}: {
  board: Board;
  item: Item;
  busy: boolean;
  onSave: (body: Record<string, unknown>) => void;
}) {
  const { t } = useTranslation();
  const [caption, setCaption] = useState(item.caption ?? '');
  const [section, setSection] = useState(item.section_id ?? '');
  const changed = caption !== (item.caption ?? '') || section !== (item.section_id ?? '');
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        onSave({
          caption,
          ...(section ? { section_id: section } : { move_to_unsorted: true }),
        });
      }}
    >
      <label className="flex flex-col gap-1.5 text-sm font-medium">
        {t('moodboards.caption')}
        <input
          className="h-10 rounded-[var(--radius-control)] border border-line bg-surface px-3 text-sm font-normal"
          maxLength={300}
          placeholder={t('moodboards.captionPlaceholder')}
          value={caption}
          onChange={(e) => setCaption(e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1.5 text-sm font-medium">
        {t('moodboards.section')}
        <Select value={section} onChange={(e) => setSection(e.target.value)}>
          <option value="">{t('moodboards.unsorted')}</option>
          {board.sections.map((s) => (
            <option key={s.id} value={s.id}>
              {s.title}
            </option>
          ))}
        </Select>
      </label>
      {changed && (
        <Button type="submit" size="sm" className="self-start" disabled={busy}>
          {t('common.save')}
        </Button>
      )}
    </form>
  );
}

function Comments({ scope, board, item }: { scope: MoodboardScope; board: Board; item: Item }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const key = [...scope.key, board.id, item.id, 'comments'];
  const team = scope.kind === 'team';
  const sharedBoard = !team || board.visibility === 'client';
  const [body, setBody] = useState('');
  const [visibility, setVisibility] = useState<'client' | 'internal'>(
    sharedBoard ? 'client' : 'internal',
  );
  const comments = useQuery({
    queryKey: key,
    queryFn: () => api<Comment[]>('GET', scope.commentsPath(board.id, item.id)),
  });
  const add = useMutation({
    mutationFn: () =>
      api<Comment>(
        'POST',
        scope.commentPost(board.id, item.id),
        team
          ? { target_type: 'moodboard_item', target_id: item.id, body: body.trim(), visibility }
          : { body: body.trim() },
      ),
    onSuccess: async () => {
      setBody('');
      await queryClient.invalidateQueries({ queryKey: key });
      await queryClient.invalidateQueries({ queryKey: [...scope.key, board.id] });
    },
  });

  return (
    <section
      className="flex flex-col gap-3 border-t border-line pt-4"
      aria-label={t('moodboards.comments')}
    >
      <h3 className="text-sm font-semibold">{t('moodboards.comments')}</h3>
      <ul className="flex flex-col gap-3">
        {(comments.data ?? []).map((c) => (
          <li key={c.id} className="text-sm">
            <span className="font-medium">{c.author_name ?? t('moodboards.someone')}</span>{' '}
            <span className="text-xs text-muted">
              {formatDate(c.created_at)}
              {team && c.visibility === 'internal' ? ` · ${t('moodboards.teamOnly')}` : ''}
            </span>
            <p className="whitespace-pre-line">{c.body}</p>
          </li>
        ))}
        {comments.data?.length === 0 && (
          <li className="text-sm text-muted">{t('moodboards.noComments')}</li>
        )}
      </ul>
      <form
        className="flex flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (body.trim()) add.mutate();
        }}
      >
        <Textarea
          aria-label={t('moodboards.writeComment')}
          placeholder={t('moodboards.writeComment')}
          rows={2}
          maxLength={5000}
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
        <div className="flex flex-wrap items-center justify-between gap-2">
          {team && sharedBoard ? (
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                className="size-4 accent-accent"
                checked={visibility === 'internal'}
                onChange={(e) => setVisibility(e.target.checked ? 'internal' : 'client')}
              />
              {t('moodboards.teamOnlyComment')}
            </label>
          ) : (
            <span />
          )}
          <Button type="submit" size="sm" disabled={add.isPending || !body.trim()}>
            {t('moodboards.send')}
          </Button>
        </div>
        {add.error && <FormMessage>{errorMessage(add.error, t)}</FormMessage>}
      </form>
    </section>
  );
}
