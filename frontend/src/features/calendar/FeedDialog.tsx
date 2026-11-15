import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Dialog } from '@/components/Dialog';
import { FormMessage } from '@/components/FormMessage';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { api } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { formatDate } from '@/lib/format';

import type { Feed, FeedCreated } from './api';

/**
 * Private iCal subscription. The secret link is shown once, right after it was created;
 * creating a new one turns the old link off.
 */
export function FeedDialog({
  path,
  queryKey,
  onClose,
}: {
  path: string;
  queryKey: readonly unknown[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [url, setUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const feed = useQuery({ queryKey, queryFn: () => api<Feed>('GET', path) });
  const create = useMutation({
    mutationFn: () => api<FeedCreated>('POST', path),
    onSuccess: async (data) => {
      setUrl(data.url);
      setCopied(false);
      await queryClient.invalidateQueries({ queryKey });
    },
  });
  const revoke = useMutation({
    mutationFn: () => api('DELETE', path),
    onSuccess: async () => {
      setUrl(null);
      await queryClient.invalidateQueries({ queryKey });
    },
  });

  const copy = async () => {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <Dialog title={t('calendar.feed.title')} onClose={onClose}>
      <p className="text-sm text-ink-soft">{t('calendar.feed.intro')}</p>
      {feed.isPending ? (
        <Spinner />
      ) : url ? (
        <div className="flex flex-col gap-2">
          <label htmlFor="feed-url" className="text-sm font-medium">
            {t('calendar.feed.yourLink')}
          </label>
          <div className="flex gap-2">
            <Input id="feed-url" readOnly value={url} onFocus={(e) => e.target.select()} />
            <Button variant="secondary" onClick={() => void copy()}>
              {copied ? t('calendar.feed.copied') : t('calendar.feed.copy')}
            </Button>
          </div>
          <p className="text-xs text-muted">{t('calendar.feed.onceHint')}</p>
          <ul className="list-disc pl-5 text-xs text-muted">
            <li>{t('calendar.feed.howApple')}</li>
            <li>{t('calendar.feed.howGoogle')}</li>
            <li>{t('calendar.feed.howOutlook')}</li>
          </ul>
        </div>
      ) : feed.data?.active ? (
        <p className="text-sm">
          {t('calendar.feed.active', { date: formatDate(feed.data.created_at!) })}
          {feed.data.last_used_at &&
            ` ${t('calendar.feed.lastUsed', { date: formatDate(feed.data.last_used_at) })}`}
        </p>
      ) : (
        <p className="text-sm text-muted">{t('calendar.feed.inactive')}</p>
      )}
      <p className="text-xs text-muted">{t('calendar.feed.privacy')}</p>
      {(create.error || revoke.error || feed.error) && (
        <FormMessage>{errorMessage(create.error ?? revoke.error ?? feed.error, t)}</FormMessage>
      )}
      <div className="flex flex-wrap justify-between gap-2">
        {feed.data?.active ? (
          <Button
            variant="ghost"
            className="text-danger"
            disabled={revoke.isPending}
            onClick={() => revoke.mutate()}
          >
            {t('calendar.feed.turnOff')}
          </Button>
        ) : (
          <span />
        )}
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onClose}>
            {t('calendar.feed.close')}
          </Button>
          {!url && (
            <Button disabled={create.isPending} onClick={() => create.mutate()}>
              {feed.data?.active ? t('calendar.feed.newLink') : t('calendar.feed.create')}
            </Button>
          )}
        </div>
      </div>
    </Dialog>
  );
}
