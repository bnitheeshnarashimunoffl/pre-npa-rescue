import { setRequestLocale } from 'next-intl/server';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { HeartPulse } from 'lucide-react';

export default async function WellnessPage({
  params
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <div className="max-w-2xl mx-auto py-8">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2 mb-2">
            <HeartPulse className="h-5 w-5 text-[hsl(var(--primary))]" />
            <Badge variant="default">Task 6.7 — Credit Wellness Simulation</Badge>
          </div>
          <CardTitle>Credit Wellness & Recovery Trajectory Shell</CardTitle>
          <CardDescription>
            Illustrative projection comparing timely plan adherence vs. NPA score impact.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-[hsl(var(--muted-foreground))]">
          Wellness view ready for simulation wiring in Task 6.7.
        </CardContent>
      </Card>
    </div>
  );
}
