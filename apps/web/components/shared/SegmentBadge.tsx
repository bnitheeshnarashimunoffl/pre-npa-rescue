import * as React from 'react';
import { useTranslations } from 'next-intl';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';

export interface SegmentBadgeProps {
  segment: 'forgot' | 'cant_pay' | 'wont_pay' | 'not_at_risk' | string;
  className?: string;
}

export function SegmentBadge({ segment, className }: SegmentBadgeProps) {
  const t = useTranslations('badges.segment');
  const normalized = segment?.toLowerCase();

  let variant: 'info' | 'warning' | 'destructive' | 'secondary' = 'secondary';
  let label = segment;

  if (normalized === 'forgot') {
    variant = 'info';
    label = t('forgot');
  } else if (normalized === 'cant_pay') {
    variant = 'warning';
    label = t('cant_pay');
  } else if (normalized === 'wont_pay') {
    variant = 'destructive';
    label = t('wont_pay');
  } else if (normalized === 'not_at_risk') {
    variant = 'secondary';
    label = t('not_at_risk');
  }

  return (
    <Badge variant={variant} className={cn('font-medium', className)}>
      <span>{label}</span>
    </Badge>
  );
}
