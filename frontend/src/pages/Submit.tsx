import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useConfigs } from "../hooks/useConfigs";
import { client } from "../api/client";
import { HydraOverridesInput, parseHydraOverrides } from "../components/HydraOverridesInput";

type Tab = "collect" | "train" | "eval";

export function Submit() {
  const [tab, setTab] = useState<Tab>("train");
  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-4">Submit a run</h1>
      <div role="tablist" className="tabs tabs-boxed mb-6">
        {(["collect", "train", "eval"] as Tab[]).map((t) => (
          <button
            key={t}
            role="tab"
            className={`tab ${tab === t ? "tab-active" : ""}`}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>
      {tab === "collect" && <CollectForm />}
      {tab === "train" && <TrainForm />}
      {tab === "eval" && <EvalForm />}
    </div>
  );
}

function useSubmitRun<T extends object>(path: "/api/v1/runs/collect" | "/api/v1/runs/train" | "/api/v1/runs/eval") {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: T) => {
      const { data, error } = await client.POST(path, { body: body as never });
      if (error) throw new Error(JSON.stringify(error));
      return data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      if (data?.run_id) navigate(`/runs/${data.run_id}`);
    },
  });
}

function CollectForm() {
  const envs = useConfigs("envs");
  const [env, setEnv] = useState("");
  const [episodes, setEpisodes] = useState(10);
  const [policyType, setPolicyType] = useState<"scripted" | "teleop">("scripted");
  const [pushToHub, setPushToHub] = useState(false);
  const [seed, setSeed] = useState<string>("");
  const [overrides, setOverrides] = useState("");
  const submit = useSubmitRun<{
    env?: string;
    episodes: number;
    policy_type: "scripted" | "teleop";
    push_to_hub: boolean;
    seed?: number;
    hydra_overrides: string[];
  }>("/api/v1/runs/collect");

  return (
    <form
      className="grid gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        submit.mutate({
          env: env || undefined,
          episodes,
          policy_type: policyType,
          push_to_hub: pushToHub,
          seed: seed ? Number(seed) : undefined,
          hydra_overrides: parseHydraOverrides(overrides),
        });
      }}
    >
      <ConfigSelect label="Env" value={env} onChange={setEnv} options={envs.data} />
      <NumberInput label="Episodes" value={episodes} onChange={setEpisodes} min={1} max={10000} />
      <label className="form-control">
        <div className="label"><span className="label-text">Policy type</span></div>
        <select
          className="select select-bordered"
          value={policyType}
          onChange={(e) => setPolicyType(e.target.value as "scripted" | "teleop")}
        >
          <option value="scripted">scripted</option>
          <option value="teleop">teleop</option>
        </select>
      </label>
      <label className="label cursor-pointer">
        <span className="label-text">Push to HF Hub</span>
        <input type="checkbox" className="checkbox" checked={pushToHub} onChange={(e) => setPushToHub(e.target.checked)} />
      </label>
      <label className="form-control">
        <div className="label"><span className="label-text">Seed (optional)</span></div>
        <input className="input input-bordered" value={seed} onChange={(e) => setSeed(e.target.value)} />
      </label>
      <HydraOverridesInput value={overrides} onChange={setOverrides} />
      <SubmitButton pending={submit.isPending} error={submit.error} />
    </form>
  );
}

function TrainForm() {
  const envs = useConfigs("envs");
  const profiles = useConfigs("profiles");
  const [policy, setPolicy] = useState<"act" | "diffusion">("act");
  const [totalSteps, setTotalSteps] = useState(10000);
  const [env, setEnv] = useState("");
  const [profile, setProfile] = useState("");
  const [hfRepoId, setHfRepoId] = useState("");
  const [overrides, setOverrides] = useState("");
  const submit = useSubmitRun<{
    policy: "act" | "diffusion";
    total_steps: number;
    env?: string;
    profile?: string;
    hf_repo_id?: string;
    hydra_overrides: string[];
  }>("/api/v1/runs/train");

  return (
    <form
      className="grid gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        submit.mutate({
          policy,
          total_steps: totalSteps,
          env: env || undefined,
          profile: profile || undefined,
          hf_repo_id: hfRepoId || undefined,
          hydra_overrides: parseHydraOverrides(overrides),
        });
      }}
    >
      <label className="form-control">
        <div className="label"><span className="label-text">Policy</span></div>
        <select className="select select-bordered" value={policy} onChange={(e) => setPolicy(e.target.value as "act" | "diffusion")}>
          <option value="act">act</option>
          <option value="diffusion">diffusion</option>
        </select>
      </label>
      <NumberInput label="Total steps" value={totalSteps} onChange={setTotalSteps} min={1} max={10_000_000} />
      <ConfigSelect label="Env" value={env} onChange={setEnv} options={envs.data} />
      <ConfigSelect label="Profile" value={profile} onChange={setProfile} options={profiles.data} />
      <label className="form-control">
        <div className="label"><span className="label-text">HF repo id (optional)</span></div>
        <input className="input input-bordered" value={hfRepoId} onChange={(e) => setHfRepoId(e.target.value)} />
      </label>
      <HydraOverridesInput value={overrides} onChange={setOverrides} />
      <SubmitButton pending={submit.isPending} error={submit.error} />
    </form>
  );
}

function EvalForm() {
  const [checkpointPath, setCheckpointPath] = useState("");
  const [nEpisodes, setNEpisodes] = useState(50);
  const [visualize, setVisualize] = useState(false);
  const [policy, setPolicy] = useState<"" | "act" | "diffusion">("");
  const [overrides, setOverrides] = useState("");
  const submit = useSubmitRun<{
    checkpoint_path: string;
    n_episodes: number;
    visualize: boolean;
    policy?: "act" | "diffusion";
    hydra_overrides: string[];
  }>("/api/v1/runs/eval");

  return (
    <form
      className="grid gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        submit.mutate({
          checkpoint_path: checkpointPath,
          n_episodes: nEpisodes,
          visualize,
          policy: policy || undefined,
          hydra_overrides: parseHydraOverrides(overrides),
        });
      }}
    >
      <label className="form-control">
        <div className="label"><span className="label-text">Checkpoint path *</span></div>
        <input
          className="input input-bordered"
          required
          value={checkpointPath}
          onChange={(e) => setCheckpointPath(e.target.value)}
          placeholder="checkpoints/{robot}/{policy}/step_XXXX.ckpt"
        />
      </label>
      <NumberInput label="N episodes" value={nEpisodes} onChange={setNEpisodes} min={1} max={1000} />
      <label className="label cursor-pointer">
        <span className="label-text">Visualize</span>
        <input type="checkbox" className="checkbox" checked={visualize} onChange={(e) => setVisualize(e.target.checked)} />
      </label>
      <label className="form-control">
        <div className="label"><span className="label-text">Policy (optional override)</span></div>
        <select className="select select-bordered" value={policy} onChange={(e) => setPolicy(e.target.value as "" | "act" | "diffusion")}>
          <option value="">(auto)</option>
          <option value="act">act</option>
          <option value="diffusion">diffusion</option>
        </select>
      </label>
      <HydraOverridesInput value={overrides} onChange={setOverrides} />
      <SubmitButton pending={submit.isPending} error={submit.error} />
    </form>
  );
}

function ConfigSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { name: string }[] | undefined;
}) {
  return (
    <label className="form-control">
      <div className="label"><span className="label-text">{label}</span></div>
      <select className="select select-bordered" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">(default)</option>
        {(options ?? []).map((o) => (
          <option key={o.name} value={o.name}>{o.name}</option>
        ))}
      </select>
    </label>
  );
}

function NumberInput({ label, value, onChange, min, max }: {
  label: string; value: number; onChange: (v: number) => void; min?: number; max?: number;
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
