import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { FormMessage } from '@/components/FormMessage';
import { Spinner } from '@/components/Spinner';
import { Card } from '@/components/ui/card';
import { api, type Schemas } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';

type Preferences = Schemas['PreferencesOut'];
type Kind = keyof Preferences;

/** Email switches for one organization; `audience` picks the wording for team or couple. */
export function NotificationSettings({
  path,
  queryKey,
  audience,
}: {
  path: string;
  queryKey: readonly unknown[];
  audience: 'team' | 'couple';
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const prefs = useQuery({ queryKey, queryFn: () => api<Preferences>('GET', path) });
  const save = useMutation({
    mutationFn: (change: Partial<Preferences>) => api<Preferences>('PATCH', path, change),
    onSuccess: (data) => queryClient.setQueryData(queryKey, data),
  });

  if (prefs.isPending) return <Spinner />;
  if (!prefs.data) return <FormMessage>{errorMessage(prefs.error, t)}</FormMessage>;
  const kinds: Kind[] = ['task_assigned', 'comments', 'documents', 'daily_digest'];
  const shown = audience === 'couple' ? kinds.filter((k) => k !== 'task_assigned') : kinds;

  return (
    <Card className="flex flex-col p-0">
      <ul>
        {shown.map((kind) => {
          const id = `notify-${kind}`;
          return (
            <li
              key={kind}
              className="flex items-start justify-between gap-4 border-b border-line-soft px-5 py-4 last:border-b-0"
            >
              <label htmlFor={id} className="flex flex-col gap-0.5">
                <span className="text-sm font-medium">
                  {t(`notifications.kinds.${kind}.title`)}
                </span>
                <span className="text-xs text-muted">
                  {t(`notifications.kinds.${kind}.${audience}`)}
                </span>
              </label>
              <input
                id={id}
                type="checkbox"
                role="switch"
                className="mt-1 size-5 shrink-0 accent-accent"
                checked={prefs.data[kind]}
                disabled={save.isPending}
                onChange={(e) => save.mutate({ [kind]: e.target.checked })}
              />
            </li>
          );
        })}
      </ul>
      {save.error && (
        <div className="px-5 pb-4">
          <FormMessage>{errorMessage(save.error, t)}</FormMessage>
        </div>
      )}
    </Card>
  );
}
