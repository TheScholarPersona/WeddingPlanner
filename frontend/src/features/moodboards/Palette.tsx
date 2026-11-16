import { X } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export function Palette({ colors, size = 'md' }: { colors: string[]; size?: 'sm' | 'md' }) {
  const { t } = useTranslation();
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label={t('moodboards.palette')}>
      {colors.map((c) => (
        <li
          key={c}
          title={c.toUpperCase()}
          className={cn('rounded-full border border-line', size === 'sm' ? 'size-5' : 'size-8')}
          style={{ backgroundColor: c }}
        >
          <span className="sr-only">{c.toUpperCase()}</span>
        </li>
      ))}
    </ul>
  );
}

/** Up to 8 colors: pick with the color picker or type a hex value. */
export function PaletteEditor({
  colors,
  onChange,
  disabled,
}: {
  colors: string[];
  onChange: (colors: string[]) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const [next, setNext] = useState('#c9a9a6');
  const valid = /^#[0-9a-f]{6}$/i.test(next);
  return (
    <div className="flex flex-wrap items-center gap-2">
      {colors.map((c) => (
        <span
          key={c}
          className="flex items-center gap-1 rounded-full border border-line bg-surface py-1 pr-1 pl-1.5 text-xs"
        >
          <span className="size-5 rounded-full border border-line" style={{ backgroundColor: c }} />
          {c.toUpperCase()}
          <button
            type="button"
            className="rounded-full p-0.5 hover:bg-subtle"
            aria-label={t('moodboards.removeColor', { color: c.toUpperCase() })}
            disabled={disabled}
            onClick={() => onChange(colors.filter((x) => x !== c))}
          >
            <X aria-hidden="true" className="size-3.5" />
          </button>
        </span>
      ))}
      {colors.length < 8 && (
        <span className="flex items-center gap-1.5">
          <input
            type="color"
            aria-label={t('moodboards.pickColor')}
            className="size-8 cursor-pointer rounded border border-line bg-surface"
            value={valid ? next : '#000000'}
            onChange={(e) => setNext(e.target.value)}
          />
          <input
            aria-label={t('moodboards.hexValue')}
            className="h-8 w-24 rounded-md border border-line bg-surface px-2 text-xs"
            value={next}
            onChange={(e) => setNext(e.target.value.trim())}
          />
          <Button
            size="sm"
            variant="secondary"
            disabled={disabled || !valid || colors.includes(next.toLowerCase())}
            onClick={() => onChange([...colors, next.toLowerCase()])}
          >
            {t('moodboards.addColor')}
          </Button>
        </span>
      )}
    </div>
  );
}
