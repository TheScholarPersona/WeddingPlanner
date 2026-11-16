import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragOverEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  rectSortingStrategy,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useQueryClient } from '@tanstack/react-query';
import { Check, Heart, ImagePlus, MessageCircle } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';

import { Badge } from '@/components/Badge';
import { Dialog } from '@/components/Dialog';
import { Field } from '@/components/Field';
import { FormMessage } from '@/components/FormMessage';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { api, downloadUrl } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { cn } from '@/lib/utils';

import {
  ACCEPT_IMAGES,
  imageUrl,
  MAX_FILES,
  MAX_IMAGE_MB,
  type Board,
  type Item,
  type MoodboardScope,
} from './api';
import { useBoard, useBoardMutation, uploadImages } from './hooks';
import { ItemDialog } from './ItemDialog';
import { Palette, PaletteEditor } from './Palette';

const UNSORTED = '';
type Order = Record<string, string[]>;

function orderOf(board: Board, showDiscarded: boolean): Order {
  const order: Order = { [UNSORTED]: [] };
  for (const s of board.sections) order[s.id] = [];
  for (const item of board.items) {
    if (item.status === 'discarded' && !showDiscarded) continue;
    (order[item.section_id ?? UNSORTED] ??= []).push(item.id);
  }
  return order;
}

export function BoardView({ scope, boardId }: { scope: MoodboardScope; boardId: string }) {
  const { t } = useTranslation();
  const board = useBoard(scope, boardId);
  if (board.isPending) return <Spinner />;
  if (!board.data) return <FormMessage>{errorMessage(board.error, t)}</FormMessage>;
  return <BoardBody scope={scope} board={board.data} />;
}

function BoardBody({ scope, board }: { scope: MoodboardScope; board: Board }) {
  const { t } = useTranslation();
  const team = scope.kind === 'team';
  const canUpload = !team || board.can_manage;
  const canSelect = team && board.can_manage;
  const [showDiscarded, setShowDiscarded] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [order, setOrder] = useState<Order>(() => orderOf(board, showDiscarded));
  const dragging = useRef(false);
  const items = useMemo(() => new Map(board.items.map((i) => [i.id, i])), [board.items]);
  const discarded = board.items.filter((i) => i.status === 'discarded').length;

  useEffect(() => {
    if (!dragging.current) setOrder(orderOf(board, showDiscarded));
  }, [board, showDiscarded]);

  const reorder = useBoardMutation(scope, board.id, (next: Order) =>
    api('POST', `${scope.base}/${board.id}/reorder`, {
      sections: board.sections.map((s) => s.id),
      items: next,
    }),
  );
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const containerOf = (id: string) =>
    id.startsWith('section:')
      ? id.slice(8)
      : Object.keys(order).find((k) => order[k]!.includes(id));

  const onDragOver = ({ active, over }: DragOverEvent) => {
    if (!over) return;
    const from = containerOf(String(active.id));
    const to = containerOf(String(over.id));
    if (from === undefined || to === undefined || from === to) return;
    setOrder((prev) => {
      const moving = String(active.id);
      const target = prev[to]!;
      const index = target.indexOf(String(over.id));
      return {
        ...prev,
        [from]: prev[from]!.filter((id) => id !== moving),
        [to]: [
          ...target.slice(0, index < 0 ? target.length : index),
          moving,
          ...target.slice(index < 0 ? target.length : index),
        ],
      };
    });
  };
  const onDragEnd = ({ active, over }: DragEndEvent) => {
    dragging.current = false;
    if (!over) return;
    const container = containerOf(String(active.id));
    if (container === undefined) return;
    const list = order[container]!;
    const from = list.indexOf(String(active.id));
    const to = list.indexOf(String(over.id));
    const next =
      from >= 0 && to >= 0 && from !== to
        ? { ...order, [container]: arrayMove(list, from, to) }
        : order;
    setOrder(next);
    // Discarded images that are hidden keep their place at the end of their section.
    const full: Order = {};
    for (const [key, ids] of Object.entries(next)) {
      const hidden = board.items
        .filter((i) => (i.section_id ?? UNSORTED) === key && !ids.includes(i.id))
        .map((i) => i.id);
      full[key] = [...ids, ...hidden.filter((id) => !Object.values(next).flat().includes(id))];
    }
    reorder.mutate(full, { onError: setError });
  };

  const sections = [
    ...board.sections.map((s) => ({ key: s.id, title: s.title })),
    { key: UNSORTED, title: t('moodboards.unsorted') },
  ];
  const openItem = openId ? items.get(openId) : undefined;
  const visibleIds = Object.values(order).flat();

  return (
    <div className="flex flex-col gap-6">
      <BoardHeader scope={scope} board={board} />
      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <span className="text-muted">
          {t('moodboards.counts', { count: board.item_count, selected: board.selected_count })}
        </span>
        {discarded > 0 && (
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              className="size-4 accent-accent"
              checked={showDiscarded}
              onChange={(e) => setShowDiscarded(e.target.checked)}
            />
            {t('moodboards.showDiscarded', { count: discarded })}
          </label>
        )}
      </div>
      {error != null && <FormMessage>{errorMessage(error, t)}</FormMessage>}
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={() => {
          dragging.current = true;
        }}
        onDragOver={board.can_manage ? onDragOver : undefined}
        onDragEnd={board.can_manage ? onDragEnd : () => (dragging.current = false)}
        onDragCancel={() => {
          dragging.current = false;
          setOrder(orderOf(board, showDiscarded));
        }}
      >
        {sections.map(({ key, title }) => {
          const ids = order[key] ?? [];
          if (key === UNSORTED && ids.length === 0 && board.sections.length > 0) return null;
          return (
            <SectionBlock
              key={key || 'unsorted'}
              scope={scope}
              board={board}
              sectionKey={key}
              title={title}
              ids={ids}
              items={items}
              sortable={board.can_manage}
              canUpload={canUpload}
              onOpen={setOpenId}
              onError={setError}
            />
          );
        })}
      </DndContext>
      {board.can_manage && <AddSection scope={scope} board={board} />}
      {openItem && (
        <ItemDialog
          key={openItem.id}
          scope={scope}
          board={board}
          item={openItem}
          canSelect={canSelect}
          onClose={() => setOpenId(null)}
          onNavigate={(dir) => {
            const index = visibleIds.indexOf(openItem.id);
            const next = visibleIds[(index + dir + visibleIds.length) % visibleIds.length];
            if (next) setOpenId(next);
          }}
        />
      )}
    </div>
  );
}

function SectionBlock({
  scope,
  board,
  sectionKey,
  title,
  ids,
  items,
  sortable,
  canUpload,
  onOpen,
  onError,
}: {
  scope: MoodboardScope;
  board: Board;
  sectionKey: string;
  title: string;
  ids: string[];
  items: Map<string, Item>;
  sortable: boolean;
  canUpload: boolean;
  onOpen: (id: string) => void;
  onError: (e: unknown) => void;
}) {
  const { t } = useTranslation();
  const { setNodeRef, isOver } = useDroppable({ id: `section:${sectionKey}` });
  return (
    <section
      ref={setNodeRef}
      aria-labelledby={`section-${sectionKey || 'unsorted'}`}
      className={cn('flex flex-col gap-3 rounded-xl p-1', isOver && 'bg-accent-soft/50')}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2
          id={`section-${sectionKey || 'unsorted'}`}
          className="font-display text-2xl font-semibold"
        >
          {title}
        </h2>
        {canUpload && (
          <UploadButton
            scope={scope}
            board={board}
            sectionId={sectionKey || null}
            onError={onError}
            label={title}
          />
        )}
      </div>
      {ids.length === 0 ? (
        <p className="rounded-lg border border-dashed border-line px-4 py-6 text-center text-sm text-muted">
          {canUpload ? t('moodboards.emptySectionUpload') : t('moodboards.emptySection')}
        </p>
      ) : (
        <SortableContext items={ids} strategy={rectSortingStrategy} disabled={!sortable}>
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {ids.map((id) => {
              const item = items.get(id);
              return item ? (
                <Tile
                  key={id}
                  scope={scope}
                  board={board}
                  item={item}
                  sectionTitle={title}
                  onOpen={onOpen}
                />
              ) : null;
            })}
          </ul>
        </SortableContext>
      )}
    </section>
  );
}

function Tile({
  scope,
  board,
  item,
  sectionTitle,
  onOpen,
}: {
  scope: MoodboardScope;
  board: Board;
  item: Item;
  sectionTitle: string;
  onOpen: (id: string) => void;
}) {
  const { t } = useTranslation();
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: item.id,
  });
  const alt = item.caption || t('moodboards.imageIn', { section: sectionTitle });
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn('relative', isDragging && 'z-10 opacity-70')}
    >
      <button
        type="button"
        {...attributes}
        {...listeners}
        onClick={() => onOpen(item.id)}
        aria-label={t('moodboards.openImage', { caption: alt })}
        className={cn(
          'group relative block aspect-[4/5] w-full overflow-hidden rounded-lg bg-subtle',
          item.status === 'selected' && 'ring-2 ring-accent ring-offset-2 ring-offset-ground',
          item.status === 'discarded' && 'opacity-40',
        )}
      >
        {item.ready ? (
          <img
            src={imageUrl(scope, board.id, item.id, 'thumb')}
            alt={alt}
            loading="lazy"
            draggable={false}
            className="size-full object-cover transition-transform group-hover:scale-[1.02]"
          />
        ) : (
          <span className="flex size-full items-center justify-center p-2 text-center text-xs text-muted">
            {item.scan_status === 'infected'
              ? t('documents.scan.infected')
              : item.scan_status === 'failed'
                ? t('documents.scan.failed')
                : t('moodboards.processing')}
          </span>
        )}
        {item.status === 'selected' && (
          <span className="absolute top-2 left-2 flex size-6 items-center justify-center rounded-full bg-accent text-white">
            <Check aria-hidden="true" className="size-4" />
            <span className="sr-only">{t('moodboards.status.selected')}</span>
          </span>
        )}
        {(item.hearts > 0 || item.comment_count > 0) && (
          <span className="absolute right-2 bottom-2 flex gap-1.5 rounded-full bg-ink/60 px-2 py-0.5 text-[11px] text-white">
            {item.hearts > 0 && (
              <span className="flex items-center gap-0.5">
                <Heart
                  aria-hidden="true"
                  className={cn('size-3', item.hearted_by_me && 'fill-white')}
                />
                {item.hearts}
              </span>
            )}
            {item.comment_count > 0 && (
              <span className="flex items-center gap-0.5">
                <MessageCircle aria-hidden="true" className="size-3" />
                {item.comment_count}
              </span>
            )}
          </span>
        )}
      </button>
      {item.caption && <p className="mt-1 line-clamp-2 text-xs text-ink-soft">{item.caption}</p>}
    </li>
  );
}

function UploadButton({
  scope,
  board,
  sectionId,
  label,
  onError,
}: {
  scope: MoodboardScope;
  board: Board;
  sectionId: string | null;
  label: string;
  onError: (e: unknown) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const send = async (files: File[]) => {
    setProblem(null);
    if (files.length > MAX_FILES) return setProblem(t('moodboards.tooMany', { max: MAX_FILES }));
    if (files.some((f) => f.size > MAX_IMAGE_MB * 1024 * 1024)) {
      return setProblem(t('moodboards.tooLarge', { max: MAX_IMAGE_MB }));
    }
    setBusy(true);
    try {
      await uploadImages(scope, board.id, files, sectionId);
      await queryClient.invalidateQueries({ queryKey: scope.key });
    } catch (e) {
      onError(e);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = '';
    }
  };

  return (
    <span className="flex items-center gap-2">
      {problem && <span className="text-xs text-danger">{problem}</span>}
      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPT_IMAGES}
        className="sr-only"
        aria-label={t('moodboards.addImagesTo', { section: label })}
        onChange={(e) => void send(Array.from(e.target.files ?? []))}
      />
      <Button variant="secondary" size="sm" disabled={busy} onClick={() => input.current?.click()}>
        <ImagePlus aria-hidden="true" className="size-4" />
        {busy ? t('documents.uploading') : t('moodboards.addImages')}
      </Button>
    </span>
  );
}

function AddSection({ scope, board }: { scope: MoodboardScope; board: Board }) {
  const { t } = useTranslation();
  const [title, setTitle] = useState('');
  const add = useBoardMutation(scope, board.id, (value: string) =>
    api('POST', `${scope.base}/${board.id}/sections`, { title: value }),
  );
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (title.trim()) add.mutate(title.trim(), { onSuccess: () => setTitle('') });
      }}
    >
      <Field id="new-section" label={t('moodboards.newSection')} className="w-64">
        <Input
          id="new-section"
          maxLength={80}
          placeholder={t('moodboards.sectionPlaceholder')}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </Field>
      <Button type="submit" variant="secondary" disabled={add.isPending || !title.trim()}>
        {t('common.add')}
      </Button>
      {add.error && <FormMessage>{errorMessage(add.error, t)}</FormMessage>}
    </form>
  );
}

function BoardHeader({ scope, board }: { scope: MoodboardScope; board: Board }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const team = scope.kind === 'team';
  const [renaming, setRenaming] = useState(false);
  const [notes, setNotes] = useState(board.notes_internal ?? '');
  const patch = useBoardMutation(scope, board.id, (body: Record<string, unknown>) =>
    api('PATCH', `${scope.base}/${board.id}`, body, { 'If-Match': `"${board.version}"` }),
  );
  const remove = async () => {
    if (!window.confirm(t('moodboards.confirmDelete', { title: board.title }))) return;
    await api('DELETE', `${scope.base}/${board.id}`);
    await queryClient.invalidateQueries({ queryKey: scope.key });
    void navigate(scope.listLink);
  };
  const pdf = (selectedOnly: boolean) =>
    downloadUrl(`${scope.base}/${board.id}/export.pdf?selected_only=${selectedOnly}`);

  return (
    <div className="flex flex-col gap-4 rounded-[var(--radius-card)] border border-line bg-surface p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-display text-3xl font-semibold">{board.title}</h2>
            {board.from_couple && <Badge tone="accent">{t('moodboards.fromCouple')}</Badge>}
            {team && !board.from_couple && board.visibility === 'client' && (
              <Badge tone="accent">{t('moodboards.shared')}</Badge>
            )}
          </div>
          {!team && board.palette.length > 0 && <Palette colors={board.palette} />}
        </div>
        <div className="flex flex-wrap gap-2">
          {board.can_manage && (
            <Button variant="ghost" size="sm" onClick={() => setRenaming(true)}>
              {t('moodboards.rename')}
            </Button>
          )}
          {team && (
            <>
              <Button asChild variant="secondary" size="sm">
                <a href={pdf(true)} download>
                  {t('moodboards.pdfSelected')}
                </a>
              </Button>
              <Button asChild variant="ghost" size="sm">
                <a href={pdf(false)} download>
                  {t('moodboards.pdfAll')}
                </a>
              </Button>
            </>
          )}
          {board.can_delete && (
            <Button variant="ghost" size="sm" className="text-danger" onClick={() => void remove()}>
              {t('common.delete')}
            </Button>
          )}
        </div>
      </div>
      {team && board.can_manage && (
        <>
          {!board.from_couple && (
            <label className="flex items-center gap-2.5 text-sm">
              <input
                type="checkbox"
                className="size-4 accent-accent"
                checked={board.visibility === 'client'}
                disabled={patch.isPending}
                onChange={(e) =>
                  patch.mutate({ visibility: e.target.checked ? 'client' : 'internal' })
                }
              />
              {t('moodboards.shareWithCouple')}
            </label>
          )}
          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-muted">{t('moodboards.palette')}</span>
            <PaletteEditor
              colors={board.palette}
              disabled={patch.isPending}
              onChange={(palette) => patch.mutate({ palette })}
            />
          </div>
          <Field id="board-notes" label={t('moodboards.notes')} hint={t('moodboards.notesHint')}>
            <Textarea
              id="board-notes"
              rows={2}
              maxLength={5000}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              onBlur={() => {
                if (notes !== (board.notes_internal ?? '')) patch.mutate({ notes_internal: notes });
              }}
            />
          </Field>
        </>
      )}
      {team && !board.can_manage && board.palette.length > 0 && <Palette colors={board.palette} />}
      {patch.error && <FormMessage>{errorMessage(patch.error, t)}</FormMessage>}
      {renaming && (
        <RenameDialog
          title={board.title}
          busy={patch.isPending}
          onClose={() => setRenaming(false)}
          onSave={(title) => patch.mutate({ title }, { onSuccess: () => setRenaming(false) })}
        />
      )}
    </div>
  );
}

function RenameDialog({
  title,
  busy,
  onSave,
  onClose,
}: {
  title: string;
  busy: boolean;
  onSave: (title: string) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [value, setValue] = useState(title);
  return (
    <Dialog title={t('moodboards.rename')} onClose={onClose}>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (value.trim()) onSave(value.trim());
        }}
      >
        <Field id="rename-board" label={t('moodboards.boardTitle')}>
          <Input
            id="rename-board"
            required
            maxLength={120}
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        </Field>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={busy}>
            {t('common.save')}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
