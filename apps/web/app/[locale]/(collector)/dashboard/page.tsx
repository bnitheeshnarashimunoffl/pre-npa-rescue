import { setRequestLocale } from 'next-intl/server';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { LayoutDashboard } from 'lucide-react';

export default async function DashboardPage({
  params
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <div className="py-6 space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2 mb-2">
            <LayoutDashboard className="h-5 w-5 text-[hsl(var(--primary))]" />
            <Badge variant="info">Task 6.3 — Collector Dashboard & Hardship Console</Badge>
          </div>
          <CardTitle>Collections & Distress Queue Shell</CardTitle>
          <CardDescription>
            Prioritised intelligent queue with explainability reason codes and compliance guard checks.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-[hsl(var(--muted-foreground))]">
          Queue interface ready for full implementation in Task 6.3.
        </CardContent>
      </Card>
    </div>
  );
}
