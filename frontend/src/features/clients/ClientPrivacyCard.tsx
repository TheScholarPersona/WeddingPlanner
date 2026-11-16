import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';

import { Dialog } from '@/components/Dialog';
import { Field } from '@/components/Field';
import { FormMessage } from '@/components/FormMessage';
import { Button } from '@/components/ui/button';
import { Card, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useReauth } from '@/features/team/useReauth';
import { api, downloadUrl, type Schemas } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';

type Summary = Schemas['EraseSummaryOut'];

/** Organization admins: data export (Art. 15/20) and erasure (Art. 17) for a client. */
export function ClientPrivacyCard({
  org,
  clientId,
  name,
}: {
  org: string;
  clientId: string;
  name: string;
}) {
  const { t } = useTranslation();
  const [erasing, setErasing] = useState(false);
  return (
    <Card className="flex flex-col gap-3">
      <CardTitle>{t('privacy.client.title')}</CardTitle>
      <p className="text-sm text-ink-soft">{t('privacy.client.intro')}</p>
      <div className="flex flex-wrap gap-2">
        <Button asChild variant="secondary">
          <a href={downloadUrl(`/orgs/${org}/clients/${clientId}/export`)} download>
            {t('privacy.client.export')}
          </a>
        </Button>
        <Button variant="ghost" className="text-danger" onClick={() => setErasing(true)}>
          {t('privacy.client.erase')}
        </Button>
      </div>
      {erasing && (
        <EraseDialog org={org} clientId={clientId} name={name} onClose={() => setErasing(false)} />
      )}
    </Card>
  );
}

function EraseDialog({
  org,
  clientId,
  name,
  onClose,
}: {
  org: string;
  clientId: string;
  name: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { run, dialog } = useReauth();
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const erase = async () => {
    setBusy(true);
    setError(null);
    try {
      await run(
        () => api<Summary>('POST', `/orgs/${org}/clients/${clientId}/erase`, { confirm }),
        async () => {
          await queryClient.invalidateQueries({ queryKey: ['org', org] });
          void navigate('/app/clients', { replace: true });
        },
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog title={t('privacy.client.eraseTitle', { name })} onClose={onClose}>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          void erase();
        }}
      >
        <p className="text-sm text-ink-soft">{t('privacy.client.eraseWarning')}</p>
        <Field id="erase-confirm" label={t('privacy.client.typeName', { name })}>
          <Input id="erase-confirm" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </Field>
        {error != null && <FormMessage>{errorMessage(error, t)}</FormMessage>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            type="submit"
            className="bg-danger hover:bg-danger"
            disabled={busy || confirm.trim() !== name.trim()}
          >
            {t('privacy.client.eraseForGood')}
          </Button>
        </div>
      </form>
      {dialog}
    </Dialog>
  );
}
