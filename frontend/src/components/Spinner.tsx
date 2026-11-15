import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';

export function Spinner({ fullPage = false }: { fullPage?: boolean }) {
  const { t } = useTranslation();
  return (
    <div
      role="status"
      className={cn('flex items-center justify-center p-8', fullPage && 'min-h-screen')}
    >
      <span
        aria-hidden="true"
        className="size-6 animate-spin rounded-full border-2 border-accent-tint border-t-accent"
      />
      <span className="sr-only">{t('common.loading')}</span>
    </div>
  );
}
