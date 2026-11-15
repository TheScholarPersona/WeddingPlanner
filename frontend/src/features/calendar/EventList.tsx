import { MapPin } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/Badge';
import { dateBadge } from '@/lib/format';

import { timeLabel, type AgendaEntry } from './api';

export type { AgendaEntry };

export function EventList({
  entries,
  onOpen,
}: {
  entries: AgendaEntry[];
  onOpen?: (id: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <ul className="flex flex-col">
      {entries.map((entry) => {
        const badge = dateBadge(entry.start_date);
        const content = (
          <>
            <span className="flex w-12 shrink-0 flex-col items-center rounded-lg bg-accent-soft py-1.5 text-accent-strong">
              <span className="text-[10px] font-semibold tracking-wide">{badge.month}</span>
              <span className="font-display text-xl leading-none font-semibold">{badge.day}</span>
            </span>
            <span className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="font-medium">{entry.title}</span>
              <span className="text-xs text-muted">
                {[entry.label, timeLabel(entry, t('calendar.allDay'))].filter(Boolean).join(' · ')}
              </span>
              {entry.location && (
                <span className="flex items-center gap-1 text-xs text-muted">
                  <MapPin aria-hidden="true" className="size-3.5" />
                  {entry.location}
                </span>
              )}
            </span>
            {entry.shared && <Badge tone="accent">{t('calendar.shared')}</Badge>}
          </>
        );
        return (
          <li key={entry.id} className="border-b border-line-soft last:border-b-0">
            {onOpen ? (
              <button
                type="button"
                className="flex w-full items-start gap-4 py-3.5 text-left hover:bg-subtle/60"
                onClick={() => onOpen(entry.id)}
              >
                {content}
              </button>
            ) : (
              <div className="flex items-start gap-4 py-3.5">{content}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
