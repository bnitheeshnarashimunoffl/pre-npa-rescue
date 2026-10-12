import type { Metadata } from 'next';
import { Inter, Noto_Sans_Tamil, Noto_Sans_Devanagari } from 'next/font/google';
import { NextIntlClientProvider } from 'next-intl';
import { getMessages, setRequestLocale } from 'next-intl/server';
import { notFound } from 'next/navigation';
import { routing, type AppLocale } from '@/i18n/routing';
import { cookies } from 'next/headers';
import { AppShell } from '@/components/layout/AppShell';
import '../globals.css';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-sans',
  display: 'swap'
});

const notoTamil = Noto_Sans_Tamil({
  subsets: ['tamil'],
  variable: '--font-tamil',
  weight: ['400', '500', '600', '700'],
  display: 'swap'
});

const notoDevanagari = Noto_Sans_Devanagari({
  subsets: ['devanagari'],
  variable: '--font-devanagari',
  weight: ['400', '500', '600', '700'],
  display: 'swap'
});

export const metadata: Metadata = {
  title: 'Pre-NPA Rescue — RBI & BIS Aligned Credit Resolution',
  description:
    'Early financial stress detection, uplift targeting, compassionate resolution & automated compliance under RBI directions and BIS standards.'
};

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export default async function LocaleLayout({
  children,
  params
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;

  if (!routing.locales.includes(locale as AppLocale)) {
    notFound();
  }

  setRequestLocale(locale);
  const messages = await getMessages();

  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get('demo_session');
  let currentRole: string | null = null;
  let username: string | null = null;

  if (sessionCookie?.value) {
    try {
      const parsed = JSON.parse(sessionCookie.value);
      currentRole = parsed.role;
      username = parsed.username;
    } catch {
      // ignore
    }
  }

  const isStaff =
    currentRole === 'collector' ||
    currentRole === 'hardship_officer' ||
    currentRole === 'admin' ||
    currentRole === 'auditor';

  return (
    <html
      lang={locale}
      className={`${inter.variable} ${notoTamil.variable} ${notoDevanagari.variable}`}
      suppressHydrationWarning
    >
      <body className="min-h-screen bg-[hsl(var(--background))] font-sans antialiased">
        <NextIntlClientProvider locale={locale} messages={messages}>
          <AppShell
            currentRole={currentRole}
            username={username}
            isStaff={isStaff}
          >
            {children}
          </AppShell>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
