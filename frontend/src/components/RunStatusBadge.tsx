interface Props {
  status: string;
}

const styles: Record<string, string> = {
  queued: "badge-ghost",
  running: "badge-info",
  succeeded: "badge-success",
  failed: "badge-error",
  cancelled: "badge-warning",
};

export function RunStatusBadge({ status }: Props) {
  const cls = styles[status] ?? "badge-neutral";
  return <span className={`badge ${cls}`}>{status}</span>;
}
