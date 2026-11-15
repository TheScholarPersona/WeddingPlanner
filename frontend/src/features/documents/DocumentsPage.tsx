import { useQuery } from '@tanstack/react-query';
import { FileText, Image } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';

import { Badge } from '@/components/Badge';
import { EmptyState } from '@/components/EmptyState';
import { FormMessage } from '@/components/FormMessage';
import { PageHeader } from '@/components/PageHeader';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Select } from '@/components/ui/select';
import { useActiveOrg } from '@/features/auth/useActiveOrg';
import { keys, weddingPath, type Wedding } from '@/features/weddings/api';
import { WeddingNav } from '@/features/weddings/WeddingNav';
import { api, downloadUrl } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { formatDate, formatFileSize } from '@/lib/format';

import { CATEGORIES, documentKeys, documentsPath, type Category, type Document } from './api';
import { DocumentDialog } from './DocumentDialog';
import { ScanStatus } from './ScanStatus';
import { UploadDialog } from './UploadDialog';

export function DocumentsPage() {
  const { t } = useTranslation();
  const { id = '' } = useParams();
  const { membership } = useActiveOrg();
  const org = membership.organization_id;
  const [uploading, setUploading] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [category, setCategory] = useState<Category | ''>('');

  const wedding = useQuery({
    queryKey: keys.wedding(org, id),
    queryFn: () => api<Wedding>('GET', weddingPath(org, id)),
  });
  const documents = useQuery({
    queryKey: documentKeys.list(org, id),
    queryFn: () => api<Document[]>('GET', documentsPath(org, id)),
    // Check again while a virus scan is running.
    refetchInterval: (query) =>
      query.state.data?.some((d) => d.current?.scan_status === 'pending') ? 3000 : false,
  });

  if (wedding.isPending || documents.isPending) return <Spinner />;
  if (!wedding.data || !documents.data) {
    return <FormMessage>{errorMessage(wedding.error ?? documents.error, t)}</FormMessage>;
  }
  const canEdit = wedding.data.permissions.includes('documents:write');
  const shown = documents.data.filter((d) => !category || d.category === category);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={
          <>
            <Link to="/app/weddings">{t('weddings.title')}</Link> /{' '}
            <Link to={`/app/weddings/${id}`}>{wedding.data.title}</Link>
          </>
        }
        title={wedding.data.title}
      />
      <WeddingNav id={id} />

      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-xs text-muted">{t('documents.category')}</span>
          <Select
            aria-label={t('documents.filterCategory')}
            className="w-56"
            value={category}
            onChange={(e) => setCategory(e.target.value as Category | '')}
          >
            <option value="">{t('documents.allCategories')}</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {t(`documents.categories.${c}`)}
              </option>
            ))}
          </Select>
        </label>
        {canEdit && <Button onClick={() => setUploading(true)}>{t('documents.upload')}</Button>}
      </div>

      {documents.data.length === 0 ? (
        <EmptyState title={t('documents.emptyTitle')} body={t('documents.emptyBody')} />
      ) : (
        <Card className="flex flex-col p-0">
          <ul>
            {shown.map((doc) => (
              <DocumentRow
                key={doc.id}
                doc={doc}
                downloadHref={downloadUrl(`${documentsPath(org, id)}/${doc.id}/download`)}
                onOpen={() => setOpenId(doc.id)}
              />
            ))}
          </ul>
          {shown.length === 0 && (
            <p className="p-6 text-sm text-muted">{t('documents.noneInCategory')}</p>
          )}
        </Card>
      )}
      <p className="text-sm text-muted">{t('documents.footnote')}</p>

      {uploading && <UploadDialog org={org} projectId={id} onClose={() => setUploading(false)} />}
      {openId && (
        <DocumentDialog
          org={org}
          projectId={id}
          documentId={openId}
          canEdit={canEdit}
          onClose={() => setOpenId(null)}
        />
      )}
    </div>
  );
}

function DocumentRow({
  doc,
  downloadHref,
  onOpen,
}: {
  doc: Document;
  downloadHref: string;
  onOpen: () => void;
}) {
  const { t } = useTranslation();
  const current = doc.current;
  const Icon = current?.content_type.startsWith('image/') ? Image : FileText;
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line-soft px-5 py-4 last:border-b-0">
      <Icon aria-hidden="true" className="size-5 shrink-0 text-muted" strokeWidth={1.6} />
      <div className="flex min-w-0 flex-[1_1_240px] flex-col gap-0.5">
        <button
          type="button"
          className="truncate text-left font-medium hover:underline"
          onClick={onOpen}
        >
          {doc.title}
        </button>
        <span className="text-xs text-muted">
          {[
            t(`documents.categories.${doc.category}`),
            current ? formatFileSize(current.size_bytes) : null,
            doc.version_count > 1
              ? t('documents.versionCount', { count: doc.version_count })
              : null,
            doc.created_by_name,
            formatDate(doc.updated_at),
          ]
            .filter(Boolean)
            .join(' · ')}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {doc.uploaded_by_type === 'client' && (
          <Badge tone="accent">{t('documents.fromCouple')}</Badge>
        )}
        {doc.visibility === 'client' && doc.uploaded_by_type === 'team' && (
          <Badge tone="accent">{t('documents.shared')}</Badge>
        )}
        {current && <ScanStatus status={current.scan_status} />}
        {current?.downloadable && (
          <Button asChild variant="secondary" size="sm">
            <a href={downloadHref} download>
              {t('documents.download')}
            </a>
          </Button>
        )}
      </div>
    </li>
  );
}
