export function ProgressBar({ percent, label }: { percent: number; label: string }) {
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuenow={percent}
      aria-valuemin={0}
      aria-valuemax={100}
      className="h-1.5 rounded-full bg-line"
    >
      <div className="h-1.5 rounded-full bg-accent" style={{ width: `${percent}%` }} />
    </div>
  );
}
