import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';

import { Badge } from '@/components/Badge';
import { Dialog } from '@/components/Dialog';
import { Field } from '@/components/Field';
import { FormMessage } from '@/components/FormMessage';
import { PageHeader } from '@/components/PageHeader';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { useActiveOrg } from '@/features/auth/useActiveOrg';
import { keys, type Template } from '@/features/weddings/api';
import { api, type Schemas } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';

export function TemplatesPage() {
  const { t } = useTranslation();
  const { membership, isAdmin } = useActiveOrg();
  const org = membership.organization_id;
  const [creating, setCreating] = useState(false);
  const templates = useQuery({
    queryKey: keys.templates(org),
    queryFn: () => api<Template[]>('GET', `/orgs/${org}/templates`),
  });

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t('templates.title')}
        subtitle={t('templates.subtitle')}
        actions={isAdmin && <Button onClick={() => setCreating(true)}>{t('templates.new')}</Button>}
      />
      {templates.isPending ? (
        <Spinner />
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4">
          {templates.data?.map((template) => (
            <Link key={template.id} to={`/app/templates/${template.id}`} className="text-ink">
              <Card className="flex h-full flex-col gap-2 p-5 hover:border-accent">
                <span className="flex items-center gap-2">
                  <span className="font-display text-2xl font-semibold">{template.name}</span>
                  {template.is_default && <Badge tone="accent">{t('templates.default')}</Badge>}
                </span>
                {template.description && (
                  <span className="text-sm text-ink-soft">{template.description}</span>
                )}
                <span className="text-xs text-muted">
                  {t('templates.counts', {
                    milestones: template.milestone_count,
                    tasks: template.task_count,
                  })}
                </span>
              </Card>
            </Link>
          ))}
        </div>
      )}
      {creating && (
        <NewTemplateDialog
          org={org}
          templates={templates.data ?? []}
          onClose={() => setCreating(false)}
        />
      )}
    </div>
  );
}

function NewTemplateDialog({
  org,
  templates,
  onClose,
}: {
  org: string;
  templates: Template[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [copyFrom, setCopyFrom] = useState(templates.find((tpl) => tpl.is_default)?.id ?? '');
  const create = useMutation({
    mutationFn: () =>
      api<Schemas['TemplateDetailOut']>('POST', `/orgs/${org}/templates`, {
        name,
        copy_from: copyFrom || null,
      }),
    onSuccess: async (template) => {
      await queryClient.invalidateQueries({ queryKey: keys.templates(org) });
      void navigate(`/app/templates/${template.id}`);
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    create.mutate();
  }

  return (
    <Dialog title={t('templates.new')} onClose={onClose}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Field id="t-name" label={t('templates.fields.name')}>
          <Input id="t-name" required value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field id="t-copy" label={t('templates.fields.startFrom')}>
          <Select id="t-copy" value={copyFrom} onChange={(e) => setCopyFrom(e.target.value)}>
            <option value="">{t('templates.empty')}</option>
            {templates.map((tpl) => (
              <option key={tpl.id} value={tpl.id}>
                {tpl.name}
              </option>
            ))}
          </Select>
        </Field>
        {create.isError && <FormMessage>{errorMessage(create.error, t)}</FormMessage>}
        <div className="flex justify-end gap-3">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={create.isPending}>
            {t('templates.create')}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
