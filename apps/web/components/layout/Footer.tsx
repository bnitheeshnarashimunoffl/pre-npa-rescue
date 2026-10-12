import * as React from 'react';
import { useTranslations } from 'next-intl';
import { ShieldAlert, Clock, ExternalLink } from 'lucide-react';

export function Footer() {
  const t = useTranslations('common');

  return (
    <footer className="border-t border-[hsl(var(--border))] bg-[hsl(var(--card))] py-6 text-xs text-[hsl(var(--muted-foreground))]">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          {/* Security and contact window notices */}
          <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-6">
            <div className="flex items-center gap-1.5 text-[hsl(var(--foreground))] font-medium">
              <ShieldAlert className="h-4 w-4 text-[hsl(var(--primary))]" aria-hidden="true" />
              <span>{t('privacyNotice')}</span>
            </div>

            <div className="flex items-center gap-1.5 text-[hsl(var(--muted-foreground))]">
              <Clock className="h-3.5 w-3.5" aria-hidden="true" />
              <span>{t('contactHours')}</span>
            </div>
          </div>

          {/* Standards & Grievance links */}
          <div className="flex items-center gap-4 text-[11px]">
            <span>IS 17802 · IS/ISO 10002 · IS 18295</span>
            <span aria-hidden="true">·</span>
            <a
              href="https://cms.rbi.org.in"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 hover:underline text-[hsl(var(--primary))]"
            >
              <span>RBI CMS Portal</span>
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}
