import { useEffect, useRef } from "react";

const STORE = "vay-tab:";

export function rememberedTab(key, fallback, allowed) {
  if (!key) return fallback;
  try {
    const stored = sessionStorage.getItem(STORE + key);
    if (!stored) return fallback;
    if (allowed && !allowed.includes(stored)) return fallback;
    return stored;
  } catch {
    return fallback;
  }
}

function writeTab(key, id) {
  if (!key || id == null || id === "") return;
  try {
    sessionStorage.setItem(STORE + key, String(id));
  } catch {
    /* private mode */
  }
}

function normalize(groups, tabs) {
  if (groups && groups.length) {
    return groups
      .map((group) => ({ tabs: (group.tabs || []).filter(Boolean) }))
      .filter((group) => group.tabs.length);
  }
  return [{ tabs: tabs || [] }];
}

export default function SectionTabs({
  label,
  groups,
  tabs,
  value,
  onChange,
  storageKey,
  trailing,
  sticky = false,
  fill = false,
  className = "",
  controlsPrefix = "",
}) {
  const listRef = useRef(null);
  const buttonRefs = useRef({});
  const normalized = normalize(groups, tabs);
  const flat = normalized.flatMap((group) => group.tabs);
  const split = normalized.length > 1;

  useEffect(() => {
    const node = buttonRefs.current[value];
    const list = listRef.current;
    if (!node || !list) return;
    const nodeRect = node.getBoundingClientRect();
    const listRect = list.getBoundingClientRect();
    if (nodeRect.left < listRect.left) {
      list.scrollLeft -= listRect.left - nodeRect.left;
    } else if (nodeRect.right > listRect.right) {
      list.scrollLeft += nodeRect.right - listRect.right;
    }
  }, [value, flat.map((tab) => tab.id).join("|")]);

  function select(id) {
    const tab = flat.find((row) => row.id === id);
    if (!tab || tab.disabled || tab.id === value) return;
    writeTab(storageKey, id);
    onChange(id);
    const node = buttonRefs.current[id];
    if (node) node.focus({ preventScroll: true });
  }

  function onKeyDown(event) {
    if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
    const enabled = flat.filter((tab) => !tab.disabled);
    if (!enabled.length) return;
    event.preventDefault();
    const index = enabled.findIndex((tab) => tab.id === value);
    let next = 0;
    if (event.key === "Home") next = 0;
    else if (event.key === "End") next = enabled.length - 1;
    else if (event.key === "ArrowRight") next = index < 0 ? 0 : (index + 1) % enabled.length;
    else next = index <= 0 ? enabled.length - 1 : index - 1;
    select(enabled[next].id);
  }

  const wrapClass = [
    "section-tabs-wrap",
    sticky ? "sticky" : "",
    fill ? "fill" : "",
    className,
  ].filter(Boolean).join(" ");

  return (
    <div className={wrapClass}>
      <div className="section-tabs" role="tablist" aria-label={label} ref={listRef} onKeyDown={onKeyDown}>
        {normalized.map((group, groupIndex) => (
          <div className={"section-tabs-group" + (split ? " split" : "")} key={groupIndex}>
            {group.tabs.map((tab) => {
              const on = tab.id === value;
              const buttonId = controlsPrefix ? controlsPrefix + "-" + tab.id : undefined;
              return (
                <button
                  type="button"
                  key={tab.id}
                  role="tab"
                  id={buttonId}
                  ref={(node) => { buttonRefs.current[tab.id] = node; }}
                  aria-selected={on}
                  aria-controls={buttonId ? controlsPrefix + "-panel-" + tab.id : undefined}
                  tabIndex={on ? 0 : -1}
                  disabled={Boolean(tab.disabled)}
                  title={tab.title || tab.label}
                  className={on ? "on" : ""}
                  onClick={() => select(tab.id)}
                >
                  <span>{tab.label}</span>
                  {tab.count != null ? <span className="section-tab-count">{tab.count}</span> : null}
                </button>
              );
            })}
          </div>
        ))}
      </div>
      {trailing ? <div className="section-tabs-trailing">{trailing}</div> : null}
    </div>
  );
}
