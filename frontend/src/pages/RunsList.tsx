import { useState } from "react";
import { Link } from "react-router-dom";
import { useRuns } from "../hooks/useRuns";
import { RunStatusBadge } from "../components/RunStatusBadge";

const STATUSES = ["", "queued", "running", "succeeded", "failed", "cancelled"];
const JOB_TYPES = ["", "collect", "train", "eval"];

export function RunsList() {
  const [status, setStatus] = useState("");
  const [jobType, setJobType] = useState("");
  const { data, isLoading, error } = useRuns({
    status: status || undefined,
    job_type: jobType || undefined,
    limit: 100,
  });

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Runs</h1>
      <div className="flex gap-3 mb-4">
        <select
          className="select select-bordered select-sm"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s || "all statuses"}
            </option>
          ))}
        </select>
        <select
          className="select select-bordered select-sm"
          value={jobType}
          onChange={(e) => setJobType(e.target.value)}
        >
          {JOB_TYPES.map((s) => (
            <option key={s} value={s}>
              {s || "all job types"}
            </option>
          ))}
        </select>
      </div>
      {isLoading && <div className="loading loading-spinner" />}
      {error && <div className="alert alert-error">{(error as Error).message}</div>}
      {data && (
        <table className="table table-zebra">
          <thead>
            <tr>
              <th>ID</th>
              <th>Type</th>
              <th>Status</th>
              <th>Created</th>
              <th>Finished</th>
              <th>Exit</th>
            </tr>
          </thead>
          <tbody>
            {data.map((r) => (
              <tr key={r.id}>
                <td>
                  <Link className="link" to={`/runs/${r.id}`}>
                    {r.id.slice(0, 8)}
                  </Link>
                </td>
                <td>{r.job_type}</td>
                <td>
                  <RunStatusBadge status={r.status} />
                </td>
                <td>{r.created_at}</td>
                <td>{r.finished_at ?? "—"}</td>
                <td>{r.exit_code ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
