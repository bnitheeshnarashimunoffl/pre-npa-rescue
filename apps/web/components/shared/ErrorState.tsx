import * as React from 'react';
import { useTranslations } from 'next-intl';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/utils';

export interface ApiErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown>;
  };
}

export interface ErrorStateProps {
  error?: ApiErrorEnvelope | Error | string | null;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({ error, onRetry, className }: ErrorStateProps) {
  const t = useTranslations('common');

  let code: string | undefined;
  let message: string | undefined;

  if (typeof error === 'string') {
    message = error;
  } else if (error instanceof Error) {
    message = error.message;
  } else if (error && 'error' in error && error.error) {
    code = error.error.code;
    message = error.error.message;
  }

  const displayMessage = message || t('errorTitle');

  return (
    <div
      role="alert"
      className={cn(
        'flex flex-col items-center justify-center rounded-xl border border-[hsl(var(--destructive)/0.3)] bg-[hsl(var(--destructive-subtle))] p-6 text-center text-[hsl(var(--foreground))]',
        className
      )}
    >
      <div className="mb-2 rounded-full bg-[hsl(var(--destructive)/0.15)] p-2.5 text-[hsl(var(--destructive))]">
        <AlertTriangle className="h-5 w-5" aria-hidden="true" />
      </div>

      {code && (
        <span className="font-mono text-xs font-semibold text-[hsl(var(--destructive))] uppercase tracking-wider mb-1">
          {code}
        </span>
      )}

      <p className="max-w-md text-sm font-medium leading-relaxed">
        {displayMessage}
      </p>

      {onRetry && (
        <Button
          variant="outline"
          size="sm"
          onClick={onRetry}
          className="mt-4 gap-1.5 border-[hsl(var(--destructive)/0.4)] text-[hsl(var(--foreground))] hover:bg-[hsl(var(--destructive)/0.1)]"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          <span>{t('retry')}</span>
        </Button>
      )}
    </div>
  );
}
