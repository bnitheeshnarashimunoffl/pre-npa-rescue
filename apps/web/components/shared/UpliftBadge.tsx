import * as React from 'react';
import { useTranslations } from 'next-intl';
import { Badge } from '@/components/ui/Badge';
import { Sparkles, CheckCircle2, AlertOctagon, UserX } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface UpliftBadgeProps {
  upliftGroup: 'persuadable' | 'sure_thing' | 'lost_cause' | 'sleeping_dog' | string;
  className?: string;
}

export function UpliftBadge({ upliftGroup, className }: UpliftBadgeProps) {
  const t = useTranslations('badges.uplift');
  const normalized = upliftGroup?.toLowerCase();

  let variant: 'success' | 'secondary' | 'warning' | 'destructive' = 'secondary';
  let Icon = Sparkles;
  let label = upliftGroup;

  if (normalized === 'persuadable') {
    variant = 'success';
    Icon = Sparkles;
    label = t('persuadable');
  } else if (normalized === 'sure_thing') {
    variant = 'secondary';
    Icon = CheckCircle2;
    label = t('sure_thing');
  } else if (normalized === 'lost_cause') {
    variant = 'warning';
    Icon = AlertOctagon;
    label = t('lost_cause');
  } else if (normalized === 'sleeping_dog') {
    variant = 'destructive';
    Icon = UserX;
    label = t('sleeping_dog');
  }

  return (
    <Badge variant={variant} className={cn('font-medium inline-flex items-center gap-1.5', className)}>
      <Icon className="h-3 w-3 shrink-0" aria-hidden="true" />
      <span>{label}</span>
    </Badge>
  );
}
