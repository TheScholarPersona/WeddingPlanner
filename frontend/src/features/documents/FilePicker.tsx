import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Label } from '@/components/ui/label';
import { formatFileSize } from '@/lib/format';

import { ACCEPT, MAX_UPLOAD_MB } from './api';

/** A file input with the accepted types and a size check before uploading. */
export function FilePicker({
  file,
  onChange,
}: {
  file: File | null;
  onChange: (file: File | null) => void;
}) {
  const { t } = useTranslation();
  const id = useId();
  const [tooLarge, setTooLarge] = useState(false);
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{t('documents.file')}</Label>
      <input
        id={id}
        type="file"
        accept={ACCEPT}
        aria-required="true"
        className="rounded-lg border border-dashed border-line bg-subtle p-4 text-sm file:mr-3 file:rounded-md file:border-0 file:bg-surface file:px-3 file:py-1.5 file:text-sm file:font-medium"
        onChange={(e) => {
          const chosen = e.target.files?.[0] ?? null;
          const large = !!chosen && chosen.size > MAX_UPLOAD_MB * 1024 * 1024;
          setTooLarge(large);
          onChange(large ? null : chosen);
        }}
      />
      <p className={tooLarge ? 'text-xs text-danger' : 'text-xs text-muted'}>
        {tooLarge
          ? t('documents.tooLarge', { max: MAX_UPLOAD_MB })
          : file
            ? `${file.name} · ${formatFileSize(file.size)}`
            : t('documents.fileHint', { max: MAX_UPLOAD_MB })}
      </p>
    </div>
  );
}
