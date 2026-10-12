import { setRequestLocale } from 'next-intl/server';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { FileSliders } from 'lucide-react';

export default async function PolicyAdminPage({
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
            <FileSliders className="h-5 w-5 text-[hsl(var(--primary))]" />
            <Badge variant="secondary">Task 6.5 — Board Policy Administration</Badge>
          </div>
          <CardTitle>Bank Policy Rules & Relief Bounds Shell</CardTitle>
          <CardDescription>
            Live view of board-approved parameters governing allowed relief types and caps.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-[hsl(var(--muted-foreground))]">
          Policy configuration interface ready for full implementation in Task 6.5.
        </CardContent>
      </Card>
    </div>
  );
}
