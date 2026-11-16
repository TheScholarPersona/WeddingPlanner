import { useTranslation } from 'react-i18next';
import { NavLink } from 'react-router';

import { cn } from '@/lib/utils';

export function WeddingNav({ id }: { id: string }) {
  const { t } = useTranslation();
  const link = ({ isActive }: { isActive: boolean }) =>
    cn(
      'border-b-2 py-3 text-sm whitespace-nowrap',
      isActive ? 'border-accent font-semibold text-ink' : 'border-transparent text-muted',
    );
  return (
    <nav
      aria-label={t('weddings.sections')}
      className="-mt-2 flex gap-7 overflow-x-auto border-b border-line"
    >
      <NavLink to={`/app/weddings/${id}`} end className={link}>
        {t('weddings.overview')}
      </NavLink>
      <NavLink to={`/app/weddings/${id}/tasks`} className={link}>
        {t('nav.tasks')}
      </NavLink>
      <NavLink to={`/app/weddings/${id}/budget`} className={link}>
        {t('nav.budget')}
      </NavLink>
      <NavLink to={`/app/weddings/${id}/documents`} className={link}>
        {t('nav.documents')}
      </NavLink>
      <NavLink to={`/app/weddings/${id}/moodboards`} className={link}>
        {t('nav.moodboards')}
      </NavLink>
      <NavLink to={`/app/weddings/${id}/calendar`} className={link}>
        {t('nav.calendar')}
      </NavLink>
    </nav>
  );
}
