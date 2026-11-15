import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { Dialog } from '@/components/Dialog';
import { Field } from '@/components/Field';
import { FormMessage } from '@/components/FormMessage';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { api, downloadUrl, upload } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { formatDate, formatFileSize } from '@/lib/format';

import { CATEGORIES, documentKeys, documentsPath, type Category, type DocumentDetail } from './api';
import { FilePicker } from './FilePicker';
import { ScanStatus } from './ScanStatus';

interface Props {
  org: string;
  projectId: string;
  documentId: string;
  canEdit: boolean;
  onClose: () => void;
}

export function DocumentDialog(props: Props) {
  const { t } = useTranslation();
  const { org, projectId, documentId, onClose } = props;
  const doc = useQuery({
    queryKey: [...documentKeys.list(org, projectId), documentId],
    queryFn: () => api<DocumentDetail>('GET', `${documentsPath(org, projectId)}/${documentId}`),
  });
  return (
    <Dialog title={doc.data?.title ?? t('documents.document')} onClose={onClose}>
      <div className="flex max-h-[75vh] flex-col gap-6 overflow-y-auto pr-1">
        {doc.data ? (
          <Body {...props} doc={doc.data} key={doc.data.version} />
        ) : doc.isError ? (
          <FormMessage>{errorMessage(doc.error, t)}</FormMessage>
        ) : (
          <Spinner />
        )}
      </div>
    </Dialog>
  );
}

function Body({ org, projectId, doc, canEdit, onClose }: Props & { doc: DocumentDetail }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const base = `${documentsPath(org, projectId)}/${doc.id}`;
  const [title, setTitle] = useState(doc.title);
  const [category, setCategory] = useState<Category>(doc.category);
  const [shared, setShared] = useState(doc.visibility === 'client');
  const [file, setFile] = useState<File | null>(null);
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: documentKeys.list(org, projectId) });

  const save = useMutation({
    mutationFn: () =>
      api<DocumentDetail>(
        'PATCH',
        base,
        { title: title.trim(), category, visibility: shared ? 'client' : 'internal' },
        { 'If-Match': `"${doc.version}"` },
      ),
    onSuccess: refresh,
  });
  const addVersion = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append('file', file!);
      return upload<DocumentDetail>(`${base}/versions`, form);
    },
    onSuccess: async () => {
      setFile(null);
      await refresh();
    },
  });
  const remove = useMutation({
    mutationFn: () => api('DELETE', base),
    onSuccess: async () => {
      await refresh();
      onClose();
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };

  return (
    <>
      {canEdit ? (
        <form className="flex flex-col gap-4" onSubmit={submit}>
          <Field id="doc-edit-title" label={t('documents.titleLabel')}>
            <Input
              id="doc-edit-title"
              value={title}
              required
              maxLength={200}
              onChange={(e) => setTitle(e.target.value)}
            />
          </Field>
          <Field id="doc-edit-category" label={t('documents.category')}>
            <Select
              id="doc-edit-category"
              value={category}
              onChange={(e) => setCategory(e.target.value as Category)}
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {t(`documents.categories.${c}`)}
                </option>
              ))}
            </Select>
          </Field>
          <label className="flex items-center gap-2.5 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-accent"
              checked={shared}
              onChange={(e) => setShared(e.target.checked)}
            />
            {t('documents.shareWithCouple')}
          </label>
          {save.error && <FormMessage>{errorMessage(save.error, t)}</FormMessage>}
          <div className="flex justify-end">
            <Button type="submit" disabled={save.isPending}>
              {t('common.save')}
            </Button>
          </div>
        </form>
      ) : (
        <p className="text-sm text-muted">{t(`documents.categories.${doc.category}`)}</p>
      )}

      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold">{t('documents.versions')}</h3>
        <ul className="flex flex-col">
          {doc.versions.map((v) => (
            <li
              key={v.id}
              className="flex flex-wrap items-center justify-between gap-2 border-t border-line-soft py-2.5 text-sm"
            >
              <span className="min-w-0">
                <span className="font-medium">v{v.number}</span> · {v.filename}
                <span className="block text-xs text-muted">
                  {formatFileSize(v.size_bytes)} · {formatDate(v.created_at)}
                  {v.uploaded_by_name ? ` · ${v.uploaded_by_name}` : ''}
                </span>
              </span>
              <span className="flex items-center gap-2">
                <ScanStatus status={v.scan_status} />
                {v.downloadable && (
                  <a
                    className="font-medium text-accent-strong underline-offset-2 hover:underline"
                    href={downloadUrl(`${base}/download?version=${v.id}`)}
                    download
                  >
                    {t('documents.download')}
                  </a>
                )}
              </span>
            </li>
          ))}
        </ul>
      </section>

      {canEdit && (
        <section className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold">{t('documents.newVersion')}</h3>
          <FilePicker file={file} onChange={setFile} />
          {addVersion.error && <FormMessage>{errorMessage(addVersion.error, t)}</FormMessage>}
          <div className="flex justify-end">
            <Button
              variant="secondary"
              disabled={!file || addVersion.isPending}
              onClick={() => addVersion.mutate()}
            >
              {addVersion.isPending ? t('documents.uploading') : t('documents.uploadVersion')}
            </Button>
          </div>
        </section>
      )}

      {canEdit && (
        <div className="flex justify-between gap-2 border-t border-line pt-4">
          <Button
            variant="ghost"
            className="text-danger"
            disabled={remove.isPending}
            onClick={() => {
              if (window.confirm(t('documents.confirmDelete'))) remove.mutate();
            }}
          >
            {t('common.delete')}
          </Button>
          {remove.error && <FormMessage>{errorMessage(remove.error, t)}</FormMessage>}
        </div>
      )}
    </>
  );
}
