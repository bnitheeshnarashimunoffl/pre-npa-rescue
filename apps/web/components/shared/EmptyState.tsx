import * as React from 'react';
import { useTranslations } from 'next-intl';
import { Inbox } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface EmptyStateProps {
  title?: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({
  title,
  description,
  icon,
  action,
  className
}: EmptyStateProps) {
  const t = useTranslations('common');

  return (
    <div
      className={cn(
        'flex min-h-[220px] flex-col items-center justify-center rounded-xl border border-dashed border-[hsl(var(--border))] bg-[hsl(var(--card))] p-8 text-center',
        className
      )}
      role="region"
      aria-label={title || t('emptyState')}
    >
      <div className="mb-3 rounded-full bg-[hsl(var(--secondary))] p-3 text-[hsl(var(--muted-foreground))]">
        {icon || <Inbox className="h-6 w-6" aria-hidden="true" />}
      </div>
      <h4 className="text-base font-semibold text-[hsl(var(--foreground))]">
        {title || t('emptyState')}
      </h4>
      {description && (
        <p className="mt-1 max-w-sm text-sm text-[hsl(var(--muted-foreground))] leading-relaxed">
          {description}
        </p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
