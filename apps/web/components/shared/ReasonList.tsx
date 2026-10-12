import * as React from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { cn } from '@/lib/utils';
import { Info } from 'lucide-react';

export interface ReasonItem {
  code: string;
  weight: number;
  text?: Record<string, string>;
}

export interface ReasonListProps {
  reasons: ReasonItem[];
  className?: string;
}

export function ReasonList({ reasons, className }: ReasonListProps) {
  const locale = useLocale();
  const t = useTranslations('reasons');

  if (!reasons || reasons.length === 0) {
    return null;
  }

  return (
    <div className={cn('space-y-3', className)}>
      <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]">
        <Info className="h-3.5 w-3.5 text-[hsl(var(--primary))]" aria-hidden="true" />
        <span>{t('title')}</span>
      </div>

      <ul className="space-y-2.5" role="list">
        {reasons.map((reason) => {
          const localizedText =
            reason.text?.[locale] ||
            reason.text?.['en'] ||
            reason.code.replace(/_/g, ' ');
          const pct = Math.round(reason.weight * 100);

          return (
            <li
              key={reason.code}
              className="rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-3 shadow-xs"
            >
              <div className="flex items-start justify-between gap-3">
                <span className="text-sm font-medium text-[hsl(var(--foreground))] leading-snug">
                  {localizedText}
                </span>
                <span className="shrink-0 font-mono text-xs font-medium text-[hsl(var(--muted-foreground))]">
                  {t('weight', { weight: pct })}
                </span>
              </div>

              {/* Accessible influence bar */}
              <div
                className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[hsl(var(--secondary))]"
                role="progressbar"
                aria-valuenow={pct}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`Impact of ${reason.code}: ${pct}%`}
              >
                <div
                  className="h-full rounded-full bg-[hsl(var(--primary))]"
                  style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
