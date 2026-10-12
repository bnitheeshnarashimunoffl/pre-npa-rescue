'use client';

import * as React from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { usePathname, useRouter } from '@/i18n/routing';
import { Globe } from 'lucide-react';
import { cn } from '@/lib/utils';

export function LanguageSwitcher({ className }: { className?: string }) {
  const t = useTranslations('common');
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();

  const handleSelect = (nextLocale: 'en' | 'ta' | 'hi') => {
    router.replace(pathname, { locale: nextLocale });
  };

  return (
    <div
      className={cn('inline-flex items-center gap-1 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-1 text-xs shadow-2xs', className)}
      role="group"
      aria-label={t('switchLanguage')}
    >
      <Globe className="h-3.5 w-3.5 ml-1 text-[hsl(var(--muted-foreground))]" aria-hidden="true" />
      <button
        type="button"
        onClick={() => handleSelect('en')}
        className={cn(
          'rounded px-2 py-1 font-medium transition-colors cursor-pointer',
          locale === 'en'
            ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] font-semibold'
            : 'text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))]'
        )}
        aria-pressed={locale === 'en'}
        lang="en"
      >
        EN
      </button>
      <button
        type="button"
        onClick={() => handleSelect('ta')}
        className={cn(
          'rounded px-2 py-1 font-medium transition-colors cursor-pointer',
          locale === 'ta'
            ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] font-semibold'
            : 'text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))]'
        )}
        aria-pressed={locale === 'ta'}
        lang="ta"
      >
        தமிழ்
      </button>
      <button
        type="button"
        onClick={() => handleSelect('hi')}
        className={cn(
          'rounded px-2 py-1 font-medium transition-colors cursor-pointer',
          locale === 'hi'
            ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] font-semibold'
            : 'text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))]'
        )}
        aria-pressed={locale === 'hi'}
        lang="hi"
      >
        हिंदी
      </button>
    </div>
  );
}
