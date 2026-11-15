import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <main
      id="main"
      className="flex min-h-screen flex-col items-center justify-center gap-3 px-4 text-center"
    >
      <h1 className="font-display text-5xl font-medium">{t('errors.notFoundTitle')}</h1>
      <p className="text-sm text-muted">{t('errors.notFoundBody')}</p>
      <Link to="/" className="text-sm font-medium text-accent">
        {t('errors.backHome')}
      </Link>
    </main>
  );
}
