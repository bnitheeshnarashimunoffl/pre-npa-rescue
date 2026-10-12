import { setRequestLocale } from 'next-intl/server';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { ShieldCheck } from 'lucide-react';

export default async function ScorecardPage({
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
            <ShieldCheck className="h-5 w-5 text-[hsl(var(--primary))]" />
            <Badge variant="success">Task 6.4 — Compliance Scorecard</Badge>
          </div>
          <CardTitle>Red-Team Results & Standards Matrix Shell</CardTitle>
          <CardDescription>
            Auditor view of attack harness runs mapped to RBI directions and BIS standards.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-[hsl(var(--muted-foreground))]">
          Scorecard interface ready for full implementation in Task 6.4.
        </CardContent>
      </Card>
    </div>
  );
}
