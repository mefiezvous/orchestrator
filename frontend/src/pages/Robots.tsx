// SPDX-FileCopyrightText: 2026 Arthur Mouraud
// SPDX-License-Identifier: Apache-2.0
import { useState, type FormEvent } from "react";
import {
  useBranchRobot,
  useCreateRobot,
  useRobotLineage,
  useRobots,
  type LineageNodeResponse,
  type RobotSpecBranchRequest,
  type RobotSpecCreateRequest,
  type RobotSpecResponse,
} from "../hooks/useRobots";

function parseList(value: string): string[] {
  return value
    .split(",")
    .map((v) => v.trim())
    .filter((v) => v.length > 0);
}

function parseRelationalFeatures(value: string): [string, string][] {
  return value
    .split(",")
    .map((pair) => pair.trim())
    .filter((pair) => pair.includes(":"))
    .map((pair) => {
      const [a, b] = pair.split(":").map((v) => v.trim());
      return [a, b] as [string, string];
    });
}

export function Robots() {
  const lineage = useRobotLineage();
  const robots = useRobots();
  const [creating, setCreating] = useState(false);
  const [branchingFrom, setBranchingFrom] = useState<string | null>(null);

  const robotsById = new Map((robots.data ?? []).map((r) => [r.id, r]));

  return (
    <div className="grid gap-6 max-w-3xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Robots</h1>
        <button
          className="btn btn-primary btn-sm"
          onClick={() => {
            setCreating((v) => !v);
            setBranchingFrom(null);
          }}
        >
          {creating ? "Cancel" : "New robot"}
        </button>
      </div>

      {creating && (
        <div className="card bg-base-200 p-4">
          <h2 className="font-semibold mb-2">New root robot</h2>
          <RobotSpecForm mode="create" onDone={() => setCreating(false)} />
        </div>
      )}

      <section>
        <h2 className="font-semibold mb-2">Lineage</h2>
        {lineage.isLoading && <div className="loading loading-spinner" />}
        {lineage.data?.length === 0 && (
          <p className="text-sm opacity-70">No robots declared yet.</p>
        )}
        <ul className="grid gap-2">
          {(lineage.data ?? []).map((node) => (
            <LineageTreeNode
              key={node.id}
              node={node}
              depth={0}
              robotsById={robotsById}
              branchingFrom={branchingFrom}
              onBranch={(id) => {
                setBranchingFrom(id);
                setCreating(false);
              }}
            />
          ))}
        </ul>
      </section>
    </div>
  );
}

function LineageTreeNode({
  node,
  depth,
  robotsById,
  branchingFrom,
  onBranch,
}: {
  node: LineageNodeResponse;
  depth: number;
  robotsById: Map<string, RobotSpecResponse>;
  branchingFrom: string | null;
  onBranch: (id: string | null) => void;
}) {
  const isBranching = branchingFrom === node.id;
  const parent = robotsById.get(node.id);

  return (
    <li style={{ marginLeft: depth * 20 }}>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-mono text-sm">{node.id}</span>
        <span className="badge badge-ghost badge-sm">{node.name}</span>
        <span className="text-xs opacity-70">v{node.version}</span>
        {node.description && <span className="text-xs opacity-60">{node.description}</span>}
        <button
          className="btn btn-xs"
          onClick={() => onBranch(isBranching ? null : node.id)}
        >
          {isBranching ? "Cancel" : "Branch"}
        </button>
      </div>
      {isBranching && (
        <div className="card bg-base-200 p-4 my-2">
          <h2 className="font-semibold mb-2">Branch from {node.id}</h2>
          {parent ? (
            <RobotSpecForm
              mode="branch"
              parentId={node.id}
              initial={parent}
              onDone={() => onBranch(null)}
            />
          ) : (
            <div className="loading loading-spinner" />
          )}
        </div>
      )}
      {(node.children ?? []).length > 0 && (
        <ul className="grid gap-2 mt-2 border-l border-base-300 pl-2">
          {(node.children ?? []).map((child) => (
            <LineageTreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              robotsById={robotsById}
              branchingFrom={branchingFrom}
              onBranch={onBranch}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

function RobotSpecForm({
  mode,
  parentId,
  initial,
  onDone,
}: {
  mode: "create" | "branch";
  parentId?: string;
  initial?: RobotSpecResponse;
  onDone: () => void;
}) {
  const createRobot = useCreateRobot();
  const branchRobot = useBranchRobot();

  const [id, setId] = useState("");
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");

  const [nJoints, setNJoints] = useState(initial?.spec.n_joints ?? 6);
  const [obsKeys, setObsKeys] = useState((initial?.spec.obs_keys ?? []).join(", "));
  const [actionDim, setActionDim] = useState(initial?.spec.action_dim ?? 6);
  const [targetPosKey, setTargetPosKey] = useState(initial?.spec.target_pos_key ?? "");
  const [successThreshold, setSuccessThreshold] = useState(initial?.spec.success_threshold ?? 0.05);
  const [maxEpisodeSteps, setMaxEpisodeSteps] = useState(initial?.spec.max_episode_steps ?? 200);
  const [eePosKey, setEePosKey] = useState(initial?.spec.ee_pos_key ?? "ee_pos");
  const [extraObsKeys, setExtraObsKeys] = useState((initial?.spec.extra_obs_keys ?? []).join(", "));
  const [relationalFeatures, setRelationalFeatures] = useState(
    (initial?.spec.relational_features ?? []).map(([a, b]) => `${a}:${b}`).join(", "),
  );

  const [taskDescription, setTaskDescription] = useState(initial?.task.task_description ?? "");
  const [fps, setFps] = useState(initial?.task.fps ?? 20);
  const [episodeLength, setEpisodeLength] = useState(initial?.task.episode_length ?? 200);
  const [seed, setSeed] = useState(initial?.task.seed ?? 42);

  const [hasAdapter, setHasAdapter] = useState(initial ? initial.adapter !== null : true);
  const [envName, setEnvName] = useState(initial?.adapter?.env_name ?? "");

  const [repoId, setRepoId] = useState(initial?.dataset.repo_id ?? "");
  const [taskId, setTaskId] = useState(initial?.dataset.task_id ?? "");
  const [datasetRoot, setDatasetRoot] = useState(initial?.dataset.root ?? "");

  const mutation = mode === "create" ? createRobot : branchRobot;

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const body: RobotSpecCreateRequest | RobotSpecBranchRequest = {
      id,
      name,
      description,
      spec: {
        n_joints: nJoints,
        obs_keys: parseList(obsKeys),
        action_dim: actionDim,
        target_pos_key: targetPosKey,
        success_threshold: successThreshold,
        max_episode_steps: maxEpisodeSteps,
        ee_pos_key: eePosKey,
        extra_obs_keys: parseList(extraObsKeys),
        relational_features: parseRelationalFeatures(relationalFeatures),
      },
      task: {
        task_description: taskDescription,
        fps,
        episode_length: episodeLength,
        seed,
      },
      adapter: hasAdapter ? { type: "mujoco_playground", env_name: envName } : null,
      dataset: {
        repo_id: repoId,
        task_id: taskId,
        root: datasetRoot,
      },
    };

    if (mode === "create") {
      createRobot.mutate(body as RobotSpecCreateRequest, { onSuccess: onDone });
    } else if (parentId) {
      branchRobot.mutate(
        { parentId, body: body as RobotSpecBranchRequest },
        { onSuccess: onDone },
      );
    }
  };

  return (
    <form className="grid gap-4" onSubmit={handleSubmit}>
      <fieldset className="grid gap-2">
        <legend className="font-semibold mb-1">Identity</legend>
        <TextInput
          label="Id *"
          value={id}
          onChange={setId}
          required
          pattern="^[a-z][a-z0-9_]{1,63}$"
          placeholder="cube_reach_v3"
        />
        <TextInput label="Name (lineage label) *" value={name} onChange={setName} required />
        <TextInput label="Description" value={description} onChange={setDescription} />
      </fieldset>

      <fieldset className="grid gap-2">
        <legend className="font-semibold mb-1">Spec</legend>
        <NumberInput label="N joints" value={nJoints} onChange={setNJoints} min={1} />
        <TextInput
          label="Obs keys (comma-separated) *"
          value={obsKeys}
          onChange={setObsKeys}
          required
          placeholder="ee_pos, cube_pos, joints"
        />
        <NumberInput label="Action dim" value={actionDim} onChange={setActionDim} min={1} />
        <TextInput label="Target pos key *" value={targetPosKey} onChange={setTargetPosKey} required />
        <TextInput label="EE pos key" value={eePosKey} onChange={setEePosKey} />
        <TextInput
          label="Extra obs keys (comma-separated)"
          value={extraObsKeys}
          onChange={setExtraObsKeys}
        />
        <TextInput
          label="Relational features (key:key, ...)"
          value={relationalFeatures}
          onChange={setRelationalFeatures}
          placeholder="cube_pos:ee_pos"
        />
        <NumberInput
          label="Success threshold"
          value={successThreshold}
          onChange={setSuccessThreshold}
          min={0}
          max={1}
          step={0.01}
        />
        <NumberInput
          label="Max episode steps"
          value={maxEpisodeSteps}
          onChange={setMaxEpisodeSteps}
          min={1}
        />
      </fieldset>

      <fieldset className="grid gap-2">
        <legend className="font-semibold mb-1">Objectifs (task)</legend>
        <TextInput label="Task description" value={taskDescription} onChange={setTaskDescription} />
        <NumberInput label="FPS" value={fps} onChange={setFps} min={1} />
        <NumberInput label="Episode length" value={episodeLength} onChange={setEpisodeLength} min={1} />
        <NumberInput label="Seed" value={seed} onChange={setSeed} />
      </fieldset>

      <fieldset className="grid gap-2">
        <legend className="font-semibold mb-1">Adapter</legend>
        <label className="label cursor-pointer justify-start gap-2">
          <input
            type="checkbox"
            className="checkbox"
            checked={hasAdapter}
            onChange={(e) => setHasAdapter(e.target.checked)}
          />
          <span className="label-text">MuJoCo Playground adapter</span>
        </label>
        {hasAdapter && (
          <TextInput label="Env name *" value={envName} onChange={setEnvName} required />
        )}
      </fieldset>

      <fieldset className="grid gap-2">
        <legend className="font-semibold mb-1">Dataset</legend>
        <TextInput
          label="HF repo id *"
          value={repoId}
          onChange={setRepoId}
          required
          placeholder="org/dataset-name"
        />
        <TextInput label="Task id *" value={taskId} onChange={setTaskId} required />
        <TextInput
          label="Root *"
          value={datasetRoot}
          onChange={setDatasetRoot}
          required
          placeholder="data/cube_reach_v3"
        />
      </fieldset>

      <SubmitButton pending={mutation.isPending} error={mutation.error} />
    </form>
  );
}

function TextInput({
  label,
  value,
  onChange,
  required,
  pattern,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  pattern?: string;
  placeholder?: string;
}) {
  return (
    <label className="form-control">
      <div className="label"><span className="label-text">{label}</span></div>
      <input
        className="input input-bordered"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        pattern={pattern}
        placeholder={placeholder}
      />
    </label>
  );
}

function NumberInput({
  label,
  value,
  onChange,
  min,
  max,
  step,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <label className="form-control">
      <div className="label"><span className="label-text">{label}</span></div>
      <input
        type="number"
        className="input input-bordered"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  );
}

function SubmitButton({ pending, error }: { pending: boolean; error: unknown }) {
  return (
    <div>
      <button type="submit" className="btn btn-primary" disabled={pending}>
        {pending ? "Submitting…" : "Submit"}
      </button>
      {error ? (
        <div className="alert alert-error mt-2 text-xs">{(error as Error).message}</div>
      ) : null}
    </div>
  );
}
