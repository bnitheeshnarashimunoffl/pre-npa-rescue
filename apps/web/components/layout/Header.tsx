'use client';

import * as React from 'react';
import { useTranslations } from 'next-intl';
import { Link, useRouter } from '@/i18n/routing';
import { LanguageSwitcher } from './LanguageSwitcher';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ShieldCheck, LogOut, HeartHandshake } from 'lucide-react';

export interface HeaderProps {
  currentRole?: string | null;
  username?: string | null;
}

export function Header({ currentRole, username }: HeaderProps) {
  const t = useTranslations('common');
  const tRoles = useTranslations('roles');
  const router = useRouter();

  const handleLogout = async () => {
    try {
      await fetch('/api/session', { method: 'DELETE' });
    } catch {
      // ignore
    }
    router.push('/');
  };

  const roleLabel = currentRole
    ? tRoles(currentRole as any) || currentRole
    : null;

  return (
    <header className="sticky top-0 z-40 border-b border-[hsl(var(--border))] bg-[hsl(var(--card)/0.95)] backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Brand identity */}
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="flex items-center gap-2.5 text-[hsl(var(--foreground))] hover:opacity-90 transition-opacity"
            aria-label={`${t('appName')} - ${t('tagline')}`}
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] shadow-xs">
              <HeartHandshake className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <span className="font-bold tracking-tight text-base sm:text-lg block leading-none">
                {t('appName')}
              </span>
              <span className="hidden sm:inline-block text-[11px] font-medium text-[hsl(var(--muted-foreground))] mt-0.5">
                {t('tagline')}
              </span>
            </div>
          </Link>

          <Badge variant="info" className="hidden md:inline-flex text-[11px] py-0 px-2">
            <ShieldCheck className="h-3 w-3" aria-hidden="true" />
            <span>{t('rbiCompliant')}</span>
          </Badge>
        </div>

        {/* Right side controls: Language + Role + Logout */}
        <div className="flex items-center gap-2 sm:gap-3">
          <LanguageSwitcher />

          {roleLabel && (
            <div className="flex items-center gap-2 pl-2 border-l border-[hsl(var(--border))]">
              <Badge variant="secondary" className="font-medium text-xs hidden sm:inline-flex">
                <span>{roleLabel}</span>
                {username && <span className="opacity-70 font-mono text-[10px]">({username})</span>}
              </Badge>

              <Button
                variant="ghost"
                size="sm"
                onClick={handleLogout}
                className="gap-1.5 text-xs text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]"
                title={t('logout')}
              >
                <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
                <span className="hidden md:inline">{t('logout')}</span>
              </Button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
