import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FileText, Image } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/Badge';
import { EmptyState } from '@/components/EmptyState';
import { Field } from '@/components/Field';
import { FormMessage } from '@/components/FormMessage';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { FilePicker } from '@/features/documents/FilePicker';
import { ScanStatus } from '@/features/documents/ScanStatus';
import { api, downloadUrl, upload, type Schemas } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { formatDate, formatFileSize } from '@/lib/format';

import { portalPath, usePortalProject } from './api';

type PortalDocument = Schemas['PortalDocument'];

export function PortalFilesPage() {
  const { t } = useTranslation();
  const { project, isPending } = usePortalProject();
  if (isPending) return <Spinner />;
  if (!project) {
    return <EmptyState title={t('portal.home.emptyTitle')} body={t('portal.home.emptyBody')} />;
  }
  return <Files projectId={project.id} />;
}

function Files({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const base = `${portalPath(projectId)}/documents`;
  const key = ['portal', projectId, 'documents'];
  const [adding, setAdding] = useState(false);
  const docs = useQuery({
    queryKey: key,
    queryFn: () => api<PortalDocument[]>('GET', base),
    refetchInterval: (query) =>
      query.state.data?.some((d) => d.file?.scan_status === 'pending') ? 3000 : false,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api('DELETE', `${base}/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
  });

  if (docs.isPending) return <Spinner />;
  if (!docs.data) return <FormMessage>{errorMessage(docs.error, t)}</FormMessage>;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-end justify-between gap-3">
        <h1 className="font-display text-4xl font-medium">{t('portal.files.title')}</h1>
        {!adding && (
          <Button size="sm" onClick={() => setAdding(true)}>
            {t('portal.files.add')}
          </Button>
        )}
      </div>
      {adding && (
        <UploadCard
          path={base}
          onDone={async () => {
            setAdding(false);
            await queryClient.invalidateQueries({ queryKey: key });
          }}
          onCancel={() => setAdding(false)}
        />
      )}
      {docs.data.length === 0 ? (
        <p className="text-sm text-muted">{t('portal.files.empty')}</p>
      ) : (
        <ul className="flex flex-col gap-2.5">
          {docs.data.map((doc) => {
            const Icon = doc.file?.content_type.startsWith('image/') ? Image : FileText;
            return (
              <li key={doc.id}>
                <Card className="flex items-center gap-3 p-4">
                  <Icon
                    aria-hidden="true"
                    className="size-6 shrink-0 text-muted"
                    strokeWidth={1.6}
                  />
                  <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="truncate font-medium">{doc.title}</span>
                    <span className="text-xs text-muted">
                      {[
                        doc.from_couple ? t('portal.files.fromYou') : doc.added_by,
                        formatDate(doc.updated_at),
                        doc.file ? formatFileSize(doc.file.size_bytes) : null,
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                  </div>
                  {doc.file && <ScanStatus status={doc.file.scan_status} />}
                  {doc.file?.downloadable && (
                    <Button asChild variant="secondary" size="sm">
                      <a href={downloadUrl(`${base}/${doc.id}/download`)} download>
                        {t('documents.download')}
                      </a>
                    </Button>
                  )}
                  {doc.can_delete && (
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={t('portal.files.deleteNamed', { title: doc.title })}
                      onClick={() => {
                        if (window.confirm(t('documents.confirmDelete'))) remove.mutate(doc.id);
                      }}
                    >
                      {t('common.delete')}
                    </Button>
                  )}
                </Card>
              </li>
            );
          })}
        </ul>
      )}
      {remove.error && <FormMessage>{errorMessage(remove.error, t)}</FormMessage>}
      <p className="text-xs text-muted">
        <Badge>{t('portal.files.privacyBadge')}</Badge> {t('portal.files.privacy')}
      </p>
    </div>
  );
}

function UploadCard({
  path,
  onDone,
  onCancel,
}: {
  path: string;
  onDone: () => Promise<void>;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const save = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append('file', file!);
      if (title.trim()) form.append('title', title.trim());
      return upload<PortalDocument[]>(path, form);
    },
    onSuccess: onDone,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (file) save.mutate();
  };
  return (
    <Card>
      <form className="flex flex-col gap-4" onSubmit={submit}>
        <FilePicker file={file} onChange={setFile} />
        <Field
          id="portal-doc-title"
          label={t('documents.titleLabel')}
          hint={t('documents.titleHint')}
        >
          <Input
            id="portal-doc-title"
            value={title}
            maxLength={200}
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        <p className="text-xs text-muted">{t('portal.files.sharedHint')}</p>
        {save.error && <FormMessage>{errorMessage(save.error, t)}</FormMessage>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onCancel}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={!file || save.isPending}>
            {save.isPending ? t('documents.uploading') : t('documents.upload')}
          </Button>
        </div>
      </form>
    </Card>
  );
}
