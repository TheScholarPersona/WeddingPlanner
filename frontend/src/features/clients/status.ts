export const CLIENT_STATUSES = ['inquiry', 'proposal', 'booked', 'completed', 'lost'] as const;

export function statusTone(status: string): 'accent' | 'neutral' | 'warning' {
  if (status === 'booked') return 'accent';
  if (status === 'inquiry' || status === 'proposal') return 'warning';
  return 'neutral';
}
