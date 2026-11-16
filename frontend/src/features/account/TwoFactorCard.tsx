import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/Badge';
import { Dialog } from '@/components/Dialog';
import { Field } from '@/components/Field';
import { FormMessage } from '@/components/FormMessage';
import { Button } from '@/components/ui/button';
import { Card, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { meQueryKey } from '@/features/auth/session';
import { useReauth } from '@/features/team/useReauth';
import { api, type Schemas } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { formatDate } from '@/lib/format';

type Status = Schemas['TwoFactorStatusOut'];
type Setup = Schemas['TwoFactorSetupOut'];
type Codes = Schemas['RecoveryCodesOut'];
const statusKey = ['me', '2fa'] as const;

export function TwoFactorCard({ required = false }: { required?: boolean }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { run, dialog } = useReauth();
  const status = useQuery({
    queryKey: statusKey,
    queryFn: () => api<Status>('GET', '/me/2fa'),
  });
  const [setup, setSetup] = useState<Setup | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [disabling, setDisabling] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: statusKey });
    await queryClient.invalidateQueries({ queryKey: meQueryKey });
  };
  const start = () => run(() => api<Setup>('POST', '/me/2fa/setup'), setSetup).catch(setError);
  const newCodes = () =>
    run(
      () => api<Codes>('POST', '/me/2fa/recovery-codes'),
      (r) => {
        setCodes(r.recovery_codes);
        void refresh();
      },
    ).catch(setError);

  const enabled = status.data?.enabled ?? false;
  return (
    <Card className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <CardTitle>{t('account.twoFactor.title')}</CardTitle>
        {status.data && (
          <Badge tone={enabled ? 'accent' : 'neutral'}>
            {enabled ? t('account.twoFactor.on') : t('account.twoFactor.off')}
          </Badge>
        )}
      </div>
      <p className="text-sm text-ink-soft">{t('account.twoFactor.intro')}</p>
      {required && !enabled && (
        <FormMessage>{t('account.twoFactor.requiredByOrganization')}</FormMessage>
      )}

      {codes ? (
        <RecoveryCodes codes={codes} onDone={() => setCodes(null)} />
      ) : setup ? (
        <SetupForm
          setup={setup}
          onEnabled={(r) => {
            setSetup(null);
            setCodes(r);
            void refresh();
          }}
          onCancel={() => setSetup(null)}
        />
      ) : enabled && status.data ? (
        <div className="flex flex-col gap-3">
          <p className="text-sm">
            {t('account.twoFactor.since', { date: formatDate(status.data.enabled_at!) })}{' '}
            {t('account.twoFactor.codesLeft', { count: status.data.recovery_codes_left })}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => void newCodes()}>
              {t('account.twoFactor.newCodes')}
            </Button>
            <Button variant="ghost" className="text-danger" onClick={() => setDisabling(true)}>
              {t('account.twoFactor.turnOff')}
            </Button>
          </div>
        </div>
      ) : (
        <div>
          <Button onClick={() => void start()}>{t('account.twoFactor.turnOn')}</Button>
        </div>
      )}
      {error != null && <FormMessage>{errorMessage(error, t)}</FormMessage>}
      {disabling && (
        <DisableDialog
          onClose={() => setDisabling(false)}
          onDone={() => {
            setDisabling(false);
            void refresh();
          }}
        />
      )}
      {dialog}
    </Card>
  );
}

function SetupForm({
  setup,
  onEnabled,
  onCancel,
}: {
  setup: Setup;
  onEnabled: (codes: string[]) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [code, setCode] = useState('');
  const enable = useMutation({
    mutationFn: () => api<Codes>('POST', '/me/2fa/enable', { code: code.trim() }),
    onSuccess: (r) => onEnabled(r.recovery_codes),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    enable.mutate();
  };
  return (
    <form className="flex flex-col gap-4" onSubmit={submit}>
      <ol className="list-decimal pl-5 text-sm text-ink-soft">
        <li>{t('account.twoFactor.step1')}</li>
        <li>{t('account.twoFactor.step2')}</li>
        <li>{t('account.twoFactor.step3')}</li>
      </ol>
      <div className="flex flex-wrap items-center gap-5">
        <img
          src={setup.qr_svg}
          alt={t('account.twoFactor.qrAlt')}
          className="size-44 rounded-lg border border-line bg-white p-1"
        />
        <div className="flex min-w-0 flex-col gap-1 text-sm">
          <span className="text-muted">{t('account.twoFactor.manual')}</span>
          <code className="rounded bg-subtle px-2 py-1 font-mono text-xs break-all">
            {setup.secret}
          </code>
        </div>
      </div>
      <Field id="totp-code" label={t('account.twoFactor.codeLabel')}>
        <Input
          id="totp-code"
          inputMode="numeric"
          autoComplete="one-time-code"
          required
          minLength={6}
          maxLength={6}
          value={code}
          onChange={(e) => setCode(e.target.value)}
        />
      </Field>
      {enable.error && <FormMessage>{errorMessage(enable.error, t)}</FormMessage>}
      <div className="flex gap-2">
        <Button type="submit" disabled={enable.isPending}>
          {t('account.twoFactor.confirm')}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
      </div>
    </form>
  );
}

function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const { t } = useTranslation();
  const download = () => {
    const blob = new Blob([`${t('account.twoFactor.codesFileHeader')}\n\n${codes.join('\n')}\n`], {
      type: 'text/plain',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'recovery-codes.txt';
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="flex flex-col gap-3">
      <FormMessage tone="success">{t('account.twoFactor.enabled')}</FormMessage>
      <p className="text-sm">{t('account.twoFactor.codesIntro')}</p>
      <ul
        aria-label={t('account.twoFactor.codesLabel')}
        className="grid grid-cols-2 gap-2 rounded-lg bg-subtle p-4 font-mono text-sm"
      >
        {codes.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={download}>
          {t('account.twoFactor.downloadCodes')}
        </Button>
        <Button onClick={onDone}>{t('account.twoFactor.savedCodes')}</Button>
      </div>
    </div>
  );
}

function DisableDialog({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { t } = useTranslation();
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const disable = useMutation({
    mutationFn: () => api('POST', '/me/2fa/disable', { password, code: code.trim() }),
    onSuccess: onDone,
  });
  return (
    <Dialog title={t('account.twoFactor.turnOffTitle')} onClose={onClose}>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          disable.mutate();
        }}
      >
        <p className="text-sm text-ink-soft">{t('account.twoFactor.turnOffBody')}</p>
        <Field id="disable-password" label={t('auth.fields.password')}>
          <Input
            id="disable-password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <Field id="disable-code" label={t('auth.twoFactor.code')}>
          <Input
            id="disable-code"
            inputMode="numeric"
            autoComplete="one-time-code"
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </Field>
        {disable.error && <FormMessage>{errorMessage(disable.error, t)}</FormMessage>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={disable.isPending}>
            {t('account.twoFactor.turnOff')}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
