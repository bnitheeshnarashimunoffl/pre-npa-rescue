'use client';

import * as React from 'react';
import { useTranslations } from 'next-intl';
import { Header } from './Header';
import { Footer } from './Footer';
import { StaffSidebar } from './StaffSidebar';
import { cn } from '@/lib/utils';

export interface AppShellProps {
  children: React.ReactNode;
  currentRole?: string | null;
  username?: string | null;
  isStaff?: boolean;
}

export function AppShell({
  children,
  currentRole,
  username,
  isStaff
}: AppShellProps) {
  const t = useTranslations('common');

  return (
    <div className="flex min-h-screen flex-col bg-[hsl(var(--background))] text-[hsl(var(--foreground))]">
      {/* Skip to main content link for keyboard / screen reader accessibility (IS 17802 / WCAG) */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-md focus:bg-[hsl(var(--primary))] focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-[hsl(var(--primary-foreground))] focus:shadow-lg focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[hsl(var(--ring))]"
      >
        {t('skipToContent')}
      </a>

      {/* Top application bar */}
      <Header currentRole={currentRole} username={username} />

      {/* Main content body with responsive layout */}
      <div className="flex flex-1">
        {isStaff && (
          <aside className="hidden lg:block">
            <StaffSidebar className="h-[calc(100vh-4rem)] sticky top-16" />
          </aside>
        )}

        <main
          id="main-content"
          tabIndex={-1}
          className={cn(
            'flex-1 focus:outline-none',
            isStaff ? 'p-4 sm:p-6 lg:p-8' : 'p-4 sm:p-6'
          )}
        >
          <div className={cn('mx-auto', isStaff ? 'max-w-7xl' : 'max-w-5xl')}>
            {children}
          </div>
        </main>
      </div>

      {/* Persistent Compliance Footer */}
      <Footer />
    </div>
  );
}
