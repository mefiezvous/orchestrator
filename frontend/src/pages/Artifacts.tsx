import { useCheckpoints, useDatasets, useEvalReports } from "../hooks/useArtifacts";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}

export function Artifacts() {
  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-bold">Artifacts</h1>
      <CheckpointsSection />
      <EvalReportsSection />
      <DatasetsSection />
    </div>
  );
}

function CheckpointsSection() {
  const { data, isLoading } = useCheckpoints();
  return (
    <section>
      <h2 className="font-semibold mb-2">Checkpoints</h2>
      {isLoading && <div className="loading loading-spinner" />}
      {data && (
        <table className="table table-sm">
          <thead>
            <tr><th>Robot</th><th>Policy</th><th>Step</th><th>Size</th><th>Modified</th><th>Path</th></tr>
          </thead>
          <tbody>
            {data.map((c) => (
              <tr key={c.path}>
                <td>{c.robot}</td>
                <td>{c.policy}</td>
                <td>{c.step}</td>
                <td>{formatBytes(c.size_bytes)}</td>
                <td>{c.modified_at}</td>
                <td className="font-mono text-xs">{c.path}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function EvalReportsSection() {
  const { data, isLoading } = useEvalReports();
  return (
    <section>
      <h2 className="font-semibold mb-2">Eval reports</h2>
      {isLoading && <div className="loading loading-spinner" />}
      {data && (
        <table className="table table-sm">
          <thead>
            <tr><th>Robot</th><th>Policy</th><th>Video</th><th>Size</th><th>Modified</th><th>Path</th></tr>
          </thead>
          <tbody>
            {data.map((r) => (
              <tr key={r.path}>
                <td>{r.robot}</td>
                <td>{r.policy}</td>
                <td>{r.has_video ? "yes" : "no"}</td>
                <td>{formatBytes(r.size_bytes)}</td>
                <td>{r.modified_at}</td>
                <td className="font-mono text-xs">{r.path}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function DatasetsSection() {
  const { data, isLoading } = useDatasets();
  return (
    <section>
      <h2 className="font-semibold mb-2">Datasets</h2>
      {isLoading && <div className="loading loading-spinner" />}
      {data && (
        <table className="table table-sm">
          <thead>
            <tr><th>Name</th><th>Size</th><th>Modified</th><th>Path</th></tr>
          </thead>
          <tbody>
            {data.map((d) => (
              <tr key={d.path}>
                <td>{d.name}</td>
                <td>{formatBytes(d.size_bytes)}</td>
                <td>{d.modified_at}</td>
                <td className="font-mono text-xs">{d.path}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
