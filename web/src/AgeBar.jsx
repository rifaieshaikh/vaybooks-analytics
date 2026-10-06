import { ageColor, ageKeysFrom, ageLabel, money } from "./format";

export function ageParts(buckets, bands) {
  const keys = ageKeysFrom(buckets, bands);
  return keys.map((key, index) => ({
    key,
    label: ageLabel(key, bands) + " days",
    value: Number(buckets?.[key]) || 0,
    color: ageColor(key, index),
  }));
}

function sharePct(value, total) {
  const base = Number(total) || 0;
  if (base <= 0) return "0%";
  const pct = ((Number(value) || 0) / base) * 100;
  return pct.toLocaleString(undefined, { maximumFractionDigits: 1, minimumFractionDigits: 0 }) + "%";
}

export default function AgeBar({ parts, title, selected, onSelect }) {
  const rows = parts || [];
  const sum = rows.reduce((total, part) => total + (Number(part.value) || 0), 0);
  const widthBase = sum || 1;

  function toggle(key) {
    if (!onSelect) return;
    onSelect(selected === key ? "" : key);
  }

  return (
    <div>
      {title ? <h4 className="quiet" style={{ marginBottom: 8 }}>{title}</h4> : null}
      <div className="owe-bar">
        {rows.map((part) => (
          <button
            key={part.key}
            type="button"
            className={selected === part.key ? "on" : ""}
            title={part.label + " " + money(part.value) + " (" + sharePct(part.value, sum) + ")"}
            aria-pressed={selected === part.key}
            aria-label={part.label}
            onClick={() => toggle(part.key)}
            style={{
              width: `${((Number(part.value) || 0) / widthBase) * 100}%`,
              background: part.color,
              minWidth: part.value ? 4 : 0,
            }}
          />
        ))}
      </div>
      <div className="legend">
        {rows.map((part) => (
          <button
            key={part.key}
            type="button"
            className={selected === part.key ? "on" : ""}
            aria-pressed={selected === part.key}
            onClick={() => toggle(part.key)}
            style={{ background: part.color, color: "#fff" }}
          >
            {part.label} {money(part.value)} ({sharePct(part.value, sum)})
          </button>
        ))}
      </div>
    </div>
  );
}
