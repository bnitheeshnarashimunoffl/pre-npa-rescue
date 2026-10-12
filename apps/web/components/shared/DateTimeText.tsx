import * as React from 'react';
import { cn } from '@/lib/utils';

export interface DateTimeTextProps extends React.HTMLAttributes<HTMLTimeElement> {
  date: string | Date | null | undefined;
  includeTime?: boolean;
}

export function formatIST(dateInput: string | Date, includeTime = true): string {
  const d = typeof dateInput === 'string' ? new Date(dateInput) : dateInput;
  if (isNaN(d.getTime())) return '—';

  return new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    ...(includeTime
      ? {
          hour: '2-digit',
          minute: '2-digit',
          hour12: false
        }
      : {})
  }).format(d);
}

export function DateTimeText({
  date,
  includeTime = true,
  className,
  ...props
}: DateTimeTextProps) {
  if (!date) {
    return <span className={cn('text-[hsl(var(--muted-foreground))]', className)}>—</span>;
  }

  const iso = typeof date === 'string' ? date : date.toISOString();
  const text = formatIST(date, includeTime);

  return (
    <time
      dateTime={iso}
      className={cn('text-sm text-[hsl(var(--foreground))]', className)}
      {...props}
    >
      {text}
      {includeTime && ' IST'}
    </time>
  );
}
