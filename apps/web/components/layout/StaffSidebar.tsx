'use client';

import * as React from 'react';
import { useTranslations } from 'next-intl';
import { Link, usePathname } from '@/i18n/routing';
import {
  LayoutDashboard,
  ShieldCheck,
  FileSliders,
  HeartPulse,
  Users
} from 'lucide-react';
import { cn } from '@/lib/utils';

export function StaffSidebar({ className }: { className?: string }) {
  const t = useTranslations('nav');
  const pathname = usePathname();

  const navItems = [
    {
      href: '/dashboard',
      label: t('collector'),
      icon: LayoutDashboard,
      active: pathname.startsWith('/dashboard')
    },
    {
      href: '/scorecard',
      label: t('scorecard'),
      icon: ShieldCheck,
      active: pathname.startsWith('/scorecard')
    },
    {
      href: '/policy',
      label: t('policy'),
      icon: FileSliders,
      active: pathname.startsWith('/policy')
    },
    {
      href: '/wellness',
      label: t('wellness'),
      icon: HeartPulse,
      active: pathname.startsWith('/wellness')
    },
    {
      href: '/',
      label: t('home'),
      icon: Users,
      active: pathname === '/'
    }
  ];

  return (
    <nav
      className={cn(
        'w-64 shrink-0 border-r border-[hsl(var(--border))] bg-[hsl(var(--card))] p-4 flex flex-col gap-1',
        className
      )}
      aria-label="Staff Navigation"
    >
      <div className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]">
        Bank Staff Console
      </div>

      <div className="space-y-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                item.active
                  ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] shadow-xs'
                  : 'text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))]'
              )}
              aria-current={item.active ? 'page' : undefined}
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
