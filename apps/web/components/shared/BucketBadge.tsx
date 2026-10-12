import * as React from 'react';
import { useTranslations } from 'next-intl';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';

export interface BucketBadgeProps {
  bucket: 'current' | 'sma0' | 'sma1' | 'sma2' | 'npa' | string;
  dpd?: number;
  className?: string;
}

export function BucketBadge({ bucket, dpd, className }: BucketBadgeProps) {
  const t = useTranslations('badges.bucket');
  const normalized = bucket?.toLowerCase();

  let variant: 'success' | 'info' | 'warning' | 'destructive' | 'secondary' = 'secondary';
  let label = bucket;

  if (normalized === 'current') {
    variant = 'success';
    label = t('current');
  } else if (normalized === 'sma0') {
    variant = 'info';
    label = t('sma0');
  } else if (normalized === 'sma1') {
    variant = 'warning';
    label = t('sma1');
  } else if (normalized === 'sma2') {
    variant = 'warning';
    label = t('sma2');
  } else if (normalized === 'npa') {
    variant = 'destructive';
    label = t('npa');
  }

  const dpdText = typeof dpd === 'number' ? ` · ${dpd} DPD` : '';

  return (
    <Badge variant={variant} className={cn('font-mono font-medium', className)}>
      <span>{label}{dpdText}</span>
    </Badge>
  );
}
