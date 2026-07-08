import { useState } from 'react';

const SHOW_LIMIT = 5;

export default function PerspectiveColumn({ perspective, tagsConfig, activeClassification, onSelect }) {
  const [open,     setOpen]     = useState(true);
  const [showMore, setShowMore] = useState(false);

  const conf = tagsConfig?.[perspective.key];
  const meta = conf 
    ? { icon: conf.icon, color: conf.color, bg: conf.dimColor } 
    : { icon: 'ti-tag', color: 'var(--ink3)', bg: 'var(--bg2)' };
  const items   = perspective.items || [];
  const visible = showMore ? items : items.slice(0, SHOW_LIMIT);
  const isActive = activeClassification?.dimension === perspective.key;

  return (
    <div className="perspective-col">
      {/* ── Section header — clickable to collapse ── */}
      <button
        className="perspective-col-head"
        onClick={() => setOpen(o => !o)}
        style={{ '--dim-color': meta.color }}
      >
        <i className={`ti ${meta.icon}`} style={{ color: meta.color }} />
        <span>{perspective.label}</span>
        <i
          className="ti ti-chevron-right persp-chevron"
          style={{ transform: open ? 'rotate(90deg)' : 'rotate(0deg)' }}
        />
      </button>

      {/* ── Items ── */}
      {open && (
        <div className="perspective-col-body">
          {visible.map(item => {
            const active = isActive && activeClassification?.value === item.name;
            return (
              <div
                key={item.name}
                className={`cls-item${active ? ' active' : ''}`}
                style={active ? { '--active-bg': meta.bg, '--active-color': meta.color } : {}}
                onClick={() => onSelect(active ? null : { dimension: perspective.key, value: item.name })}
              >
                <span className="cls-name">{item.name}</span>
                <span className="cls-count" style={active ? { color: meta.color, background: meta.bg } : {}}>
                  {item.count}
                </span>
              </div>
            );
          })}

          {items.length > SHOW_LIMIT && (
            <button className="cls-show-more" onClick={() => setShowMore(s => !s)}>
              {showMore ? 'Show less ↑' : `+${items.length - SHOW_LIMIT} more`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
