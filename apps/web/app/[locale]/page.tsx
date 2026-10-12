import { setRequestLocale } from 'next-intl/server';
import { RolePicker } from '@/components/demo/RolePicker';

export default async function HomePage({
  params
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  return <RolePicker />;
}
