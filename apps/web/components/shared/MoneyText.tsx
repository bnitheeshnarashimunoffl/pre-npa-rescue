import * as React from 'react';
import { cn } from '@/lib/utils';

export interface MoneyTextProps extends React.HTMLAttributes<HTMLSpanElement> {
  paise: number | null | undefined;
  showZero?: boolean;
}

export function formatINR(paise: number): string {
  const rupees = paise / 100;
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0
  }).format(rupees);
}

export function MoneyText({
  paise,
  showZero = true,
  className,
  ...props
}: MoneyTextProps) {
  if (paise === null || paise === undefined) {
    return <span className={cn('text-[hsl(var(--muted-foreground))]', className)}>—</span>;
  }

  if (paise === 0 && !showZero) {
    return <span className={cn('text-[hsl(var(--muted-foreground))]', className)}>—</span>;
  }

  const formatted = formatINR(paise);

  return (
    <span
      className={cn('font-mono font-medium tracking-tight text-[hsl(var(--foreground))]', className)}
      aria-label={`${formatted} Indian Rupees`}
      {...props}
    >
      {formatted}
    </span>
  );
}
