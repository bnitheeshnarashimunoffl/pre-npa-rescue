'use client';

import * as React from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from '@/i18n/routing';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import {
  UserCheck,
  HeartHandshake,
  LayoutDashboard,
  ShieldAlert,
  FileSliders,
  ShieldCheck,
  ArrowRight,
  Sparkles
} from 'lucide-react';

export function RolePicker() {
  const t = useTranslations('landing');
  const router = useRouter();
  const [loadingUser, setLoadingUser] = React.useState<string | null>(null);

  const selectPersona = async (username: string, defaultPath: string, localeOverride?: string) => {
    setLoadingUser(username);
    try {
      await fetch('/api/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username })
      });
      if (localeOverride) {
        router.push(defaultPath, { locale: localeOverride as any });
      } else {
        router.push(defaultPath);
      }
    } catch {
      router.push(defaultPath);
    } finally {
      setLoadingUser(null);
    }
  };

  const personas = [
    {
      id: 'priya',
      username: 'priya',
      icon: UserCheck,
      badgeVariant: 'info' as const,
      badgeText: t('priya.badge'),
      title: t('priya.title'),
      desc: t('priya.desc'),
      actionText: t('priya.action'),
      path: '/chat',
      locale: 'ta', // Priya gets Tamil chat demo flow per spec
      featured: true
    },
    {
      id: 'ravi',
      username: 'ravi',
      icon: HeartHandshake,
      badgeVariant: 'warning' as const,
      badgeText: t('ravi.badge'),
      title: t('ravi.title'),
      desc: t('ravi.desc'),
      actionText: t('ravi.action'),
      path: '/chat',
      locale: 'en', // Ravi gets English zero-capacity care flow per spec
      featured: true
    },
    {
      id: 'collector',
      username: 'collector1',
      icon: LayoutDashboard,
      badgeVariant: 'default' as const,
      badgeText: t('collector.badge'),
      title: t('collector.title'),
      desc: t('collector.desc'),
      actionText: t('collector.action'),
      path: '/dashboard'
    },
    {
      id: 'hardship',
      username: 'officer1',
      icon: ShieldAlert,
      badgeVariant: 'warning' as const,
      badgeText: t('hardship.badge'),
      title: t('hardship.title'),
      desc: t('hardship.desc'),
      actionText: t('hardship.action'),
      path: '/dashboard?view=hardship'
    },
    {
      id: 'admin',
      username: 'admin1',
      icon: FileSliders,
      badgeVariant: 'secondary' as const,
      badgeText: t('admin.badge'),
      title: t('admin.title'),
      desc: t('admin.desc'),
      actionText: t('admin.action'),
      path: '/policy'
    },
    {
      id: 'auditor',
      username: 'auditor1',
      icon: ShieldCheck,
      badgeVariant: 'success' as const,
      badgeText: t('auditor.badge'),
      title: t('auditor.title'),
      desc: t('auditor.desc'),
      actionText: t('auditor.action'),
      path: '/scorecard'
    }
  ];

  return (
    <div className="py-6 sm:py-10">
      {/* Hero header */}
      <div className="text-center max-w-3xl mx-auto mb-10">
        <Badge variant="info" className="mb-3 px-3 py-1 text-xs">
          <Sparkles className="h-3.5 w-3.5 mr-1" aria-hidden="true" />
          <span>Interactive Fintech Hackathon Showcase</span>
        </Badge>
        <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-[hsl(var(--foreground))]">
          {t('title')}
        </h1>
        <p className="mt-3 text-base sm:text-lg text-[hsl(var(--muted-foreground))] leading-relaxed">
          {t('subtitle')}
        </p>
        <p className="mt-2 text-sm font-medium text-[hsl(var(--primary))]">
          {t('instructions')}
        </p>
      </div>

      {/* Grid of persona cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {personas.map((persona) => {
          const Icon = persona.icon;
          const isLoading = loadingUser === persona.username;

          return (
            <Card
              key={persona.id}
              className={`flex flex-col justify-between transition-all hover:shadow-md hover:border-[hsl(var(--primary)/0.4)] ${
                persona.featured ? 'border-[hsl(var(--primary)/0.3)] bg-[hsl(var(--card))]' : ''
              }`}
            >
              <CardHeader>
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[hsl(var(--secondary))] text-[hsl(var(--primary))]">
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </div>
                  <Badge variant={persona.badgeVariant}>
                    {persona.badgeText}
                  </Badge>
                </div>
                <CardTitle className="text-lg font-bold">
                  {persona.title}
                </CardTitle>
                <CardDescription className="pt-1 text-xs sm:text-sm">
                  {persona.desc}
                </CardDescription>
              </CardHeader>

              <CardFooter className="pt-2">
                <Button
                  className="w-full justify-between group"
                  variant={persona.featured ? 'default' : 'secondary'}
                  disabled={isLoading}
                  onClick={() => selectPersona(persona.username, persona.path, persona.locale)}
                >
                  <span>{isLoading ? 'Loading session...' : persona.actionText}</span>
                  <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" aria-hidden="true" />
                </Button>
              </CardFooter>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
