import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { Dialog } from '@/components/Dialog';
import { Field } from '@/components/Field';
import { FormMessage } from '@/components/FormMessage';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { upload } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';

import { CATEGORIES, documentKeys, documentsPath, type Category, type DocumentDetail } from './api';
import { FilePicker } from './FilePicker';

export function UploadDialog({
  org,
  projectId,
  onClose,
}: {
  org: string;
  projectId: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState<Category>('other');
  const [shared, setShared] = useState(false);

  const save = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append('file', file!);
      if (title.trim()) form.append('title', title.trim());
      form.append('category', category);
      form.append('visibility', shared ? 'client' : 'internal');
      return upload<DocumentDetail>(documentsPath(org, projectId), form);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: documentKeys.list(org, projectId) });
      onClose();
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (file) save.mutate();
  };

  return (
    <Dialog title={t('documents.upload')} onClose={onClose}>
      <form className="flex flex-col gap-4" onSubmit={submit}>
        <FilePicker file={file} onChange={setFile} />
        <Field id="doc-title" label={t('documents.titleLabel')} hint={t('documents.titleHint')}>
          <Input
            id="doc-title"
            value={title}
            maxLength={200}
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        <Field id="doc-category" label={t('documents.category')}>
          <Select
            id="doc-category"
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
        <label className="flex items-start gap-2.5 text-sm">
          <input
            type="checkbox"
            className="mt-0.5 size-4 accent-accent"
            checked={shared}
            onChange={(e) => setShared(e.target.checked)}
          />
          <span>
            {t('documents.shareWithCouple')}
            <span className="block text-xs text-muted">{t('documents.shareHint')}</span>
          </span>
        </label>
        {save.error && <FormMessage>{errorMessage(save.error, t)}</FormMessage>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={!file || save.isPending}>
            {save.isPending ? t('documents.uploading') : t('documents.upload')}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
