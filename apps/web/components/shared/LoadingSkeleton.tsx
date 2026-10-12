import * as React from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils';

export interface LoadingSkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  count?: number;
}

export function LoadingSkeleton({
  count = 1,
  className,
  ...props
}: LoadingSkeletonProps) {
  const t = useTranslations('common');

  return (
    <div
      role="status"
      aria-label={t('loading')}
      className="space-y-3 w-full"
      {...props}
    >
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className={cn(
            'h-10 w-full animate-pulse rounded-lg bg-[hsl(var(--muted))]',
            className
          )}
        />
      ))}
      <span className="sr-only">{t('loading')}</span>
    </div>
  );
}
