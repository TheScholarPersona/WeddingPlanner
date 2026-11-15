import { Card } from '@/components/ui/card';

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <Card className="flex flex-col gap-2 py-10 text-center">
      <h2 className="font-display text-3xl font-medium">{title}</h2>
      <p className="mx-auto max-w-md text-sm text-muted">{body}</p>
    </Card>
  );
}
