interface Props {
  value: string;
  onChange: (value: string) => void;
}

export function HydraOverridesInput({ value, onChange }: Props) {
  return (
    <label className="form-control">
      <div className="label">
        <span className="label-text">Hydra overrides (one per line, e.g. <code>training.lr=1e-4</code>)</span>
      </div>
      <textarea
        className="textarea textarea-bordered font-mono text-xs h-32"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="key=value"
      />
    </label>
  );
}

export function parseHydraOverrides(raw: string): string[] {
  return raw
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0 && !l.startsWith("#"));
}
