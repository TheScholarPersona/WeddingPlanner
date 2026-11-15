import { useMutation } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { Dialog } from '@/components/Dialog';
import { FormMessage } from '@/components/FormMessage';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { api } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';

export function ReauthDialog({
  onCancel,
  onConfirmed,
}: {
  onCancel: () => void;
  onConfirmed: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const [password, setPassword] = useState('');
  const confirm = useMutation({
    mutationFn: () => api('POST', '/auth/reauth', { password }),
    onSuccess: () => onConfirmed(),
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    confirm.mutate();
  }

  return (
    <Dialog title={t('auth.reauth.title')} onClose={onCancel}>
      <p className="text-sm text-muted">{t('auth.reauth.body')}</p>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <Label htmlFor="reauth-password">{t('auth.fields.password')}</Label>
          <Input
            id="reauth-password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {confirm.isError && <FormMessage>{errorMessage(confirm.error, t)}</FormMessage>}
        <div className="flex justify-end gap-3">
          <Button type="button" variant="secondary" onClick={onCancel}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={confirm.isPending}>
            {t('auth.reauth.submit')}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
