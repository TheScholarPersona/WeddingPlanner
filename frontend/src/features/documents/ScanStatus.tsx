import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/Badge';

/** Shows why a file cannot be opened yet; nothing for files that are ready. */
export function ScanStatus({ status }: { status: string }) {
  const { t } = useTranslation();
  if (status === 'clean' || status === 'not_scanned') return null;
  const tone = status === 'pending' ? 'neutral' : 'danger';
  return <Badge tone={tone}>{t(`documents.scan.${status}` as never)}</Badge>;
}
