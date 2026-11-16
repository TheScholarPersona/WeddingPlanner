import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/Badge';
import { Card, CardTitle } from '@/components/ui/card';
import { api, type Schemas } from '@/lib/api/client';
import { formatDate } from '@/lib/format';

type CoupleConsents = Schemas['CoupleConsentsOut'];

/** What the couple allowed (portfolio, review request), as they decided in their portal. */
export function CoupleConsentsCard({ org, projectId }: { org: string; projectId: string }) {
  const { t } = useTranslation();
  const consents = useQuery({
    queryKey: ['org', org, 'wedding', projectId, 'consents'],
    queryFn: () => api<CoupleConsents[]>('GET', `/orgs/${org}/projects/${projectId}/consents`),
  });
  if (!consents.data?.length) return null;
  return (
    <Card className="flex flex-col gap-3">
      <CardTitle>{t('privacy.consents.title')}</CardTitle>
      <p className="text-xs text-muted">{t('privacy.consents.plannerHint')}</p>
      {consents.data.map((person) => (
        <div key={person.full_name} className="flex flex-col gap-1.5">
          <span className="text-sm font-medium">{person.full_name}</span>
          <ul className="flex flex-col gap-1">
            {person.consents.map((c) => (
              <li key={c.kind} className="flex items-center justify-between gap-2 text-sm">
                <span>{t(`privacy.consents.kinds.${c.kind}.short`)}</span>
                <Badge tone={c.granted ? 'accent' : c.granted === false ? 'danger' : 'neutral'}>
                  {c.granted == null
                    ? t('privacy.consents.notDecided')
                    : c.granted
                      ? t('privacy.consents.yesSince', { date: formatDate(c.decided_at!) })
                      : t('privacy.consents.no')}
                </Badge>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </Card>
  );
}
