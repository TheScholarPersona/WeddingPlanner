import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { ProgressBar } from '@/components/ProgressBar';
import { dateBadge } from '@/lib/format';

import type { WeddingSummary } from './api';

export function WeddingRow({ wedding }: { wedding: WeddingSummary }) {
  const { t } = useTranslation();
  const badge = wedding.wedding_date ? dateBadge(wedding.wedding_date) : null;
  const details = [
    wedding.venue_name,
    wedding.guest_count_planned != null
      ? t('weddings.guests', { count: wedding.guest_count_planned })
      : null,
    wedding.lead_name ? t('weddings.leadBy', { name: wedding.lead_name }) : null,
  ].filter(Boolean);

  return (
    <Link
      to={`/app/weddings/${wedding.id}`}
      className="grid grid-cols-[64px_minmax(0,1fr)] items-center gap-4 border-b border-line-soft py-3.5 text-ink last:border-b-0 sm:grid-cols-[64px_minmax(0,1fr)_140px_88px]"
    >
      <div className="flex flex-col items-center rounded-[10px] bg-subtle py-2">
        {badge ? (
          <>
            <span className="text-[11px] font-semibold text-muted">{badge.month}</span>
            <span className="font-display text-[26px] leading-none font-semibold">{badge.day}</span>
          </>
        ) : (
          <span className="py-2 text-xs text-muted">{t('weddings.noDate')}</span>
        )}
      </div>
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="truncate text-[15px] font-semibold">{wedding.title}</span>
        <span className="truncate text-sm text-muted">{details.join(' · ')}</span>
      </div>
      <div className="col-span-2 flex flex-col gap-1.5 sm:col-span-1">
        <ProgressBar
          percent={wedding.progress.percent}
          label={t('weddings.progressFor', { title: wedding.title })}
        />
        <span className="text-xs text-muted">
          {t('weddings.complete', { percent: wedding.progress.percent })}
        </span>
      </div>
      <span className="hidden text-right text-sm text-muted sm:block">
        {wedding.days_to_go != null && wedding.days_to_go >= 0
          ? t('weddings.daysToGo', { count: wedding.days_to_go })
          : ''}
      </span>
    </Link>
  );
}
