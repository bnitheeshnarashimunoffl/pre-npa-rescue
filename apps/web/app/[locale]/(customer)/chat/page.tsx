import { setRequestLocale } from 'next-intl/server';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { MessageSquareText } from 'lucide-react';

export default async function ChatPage({
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
            <MessageSquareText className="h-5 w-5 text-[hsl(var(--primary))]" />
            <Badge variant="info">Task 6.2 — Customer Chat</Badge>
          </div>
          <CardTitle>Multilingual Hardship Chat Shell</CardTitle>
          <CardDescription>
            Dedicated chat interface for Priya (Tamil) and Ravi (English zero-capacity path).
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-[hsl(var(--muted-foreground))]">
          Chat UI ready for conversation logic wiring in Task 6.2.
        </CardContent>
      </Card>
    </div>
  );
}
