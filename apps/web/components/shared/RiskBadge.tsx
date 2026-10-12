import * as React from 'react';
import { useTranslations } from 'next-intl';
import { Badge } from '@/components/ui/Badge';
import { ShieldAlert, ShieldCheck, Shield } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface RiskBadgeProps {
  band: 'low' | 'medium' | 'high' | string;
  probability?: number;
  className?: string;
}

export function RiskBadge({ band, probability, className }: RiskBadgeProps) {
  const t = useTranslations('badges.risk');
  const normalized = band?.toLowerCase();

  let variant: 'success' | 'warning' | 'destructive' | 'secondary' = 'secondary';
  let Icon = Shield;
  let label = band;

  if (normalized === 'low') {
    variant = 'success';
    Icon = ShieldCheck;
    label = t('low');
  } else if (normalized === 'medium') {
    variant = 'warning';
    Icon = Shield;
    label = t('medium');
  } else if (normalized === 'high') {
    variant = 'destructive';
    Icon = ShieldAlert;
    label = t('high');
  }

  const probText =
    typeof probability === 'number'
      ? ` (${Math.round(probability * 100)}%)`
      : '';

  return (
    <Badge variant={variant} className={cn('font-medium', className)}>
      <Icon className="h-3 w-3" aria-hidden="true" />
      <span>{label}{probText}</span>
    </Badge>
  );
}
