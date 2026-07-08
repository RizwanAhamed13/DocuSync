import { useState, useEffect } from 'react';
import { downloadUrl, fetchDocumentInsights } from '../lib/api.js';
import { fileIcon, highlightText } from '../lib/utils.js';

const DIM_META = {
  subject:            { label: 'Subject',            color: 'var(--tint-blue)',   bg: 'var(--tint-blue-dim)',   icon: 'ti-atom' },
  field:              { label: 'Field',              color: 'var(--tint-purple)', bg: 'var(--tint-purple-dim)', icon: 'ti-world' },
  doc_type:           { label: 'Document Type',      color: 'var(--tint-green)',  bg: 'var(--tint-green-dim)',  icon: 'ti-file-check' },
  methodology:        { label: 'Methodology',        color: 'var(--tint-orange)', bg: 'var(--tint-orange-dim)', icon: 'ti-test-pipe' },
  education_level:    { label: 'Education Level',    color: 'var(--tint-teal)',   bg: 'var(--tint-teal-dim)',   icon: 'ti-school' },
  application_domain: { label: 'Application Domain', color: 'var(--tint-indigo)', bg: 'var(--tint-indigo-dim)', icon: 'ti-cpu' },
  study_design:       { label: 'Study Design',       color: 'var(--tint-pink)',   bg: 'var(--tint-pink-dim)',   icon: 'ti-microscope' },
};

function Section({ title, icon, color, defaultOpen = false, resetKey, children, empty }) {
  const [open, setOpen] = useState(defaultOpen);
  // Reset to defaultOpen whenever the parent doc changes (resetKey changes)
  useEffect(() => { setOpen(defaultOpen); }, [resetKey]);
  if (empty) return null;
  return (
    <div className={`insp-section${open ? ' open' : ''}`}>
      <button className="insp-section-hd" onClick={() => setOpen(o => !o)}>
        <span className="insp-section-icon" style={{ background: `color-mix(in srgb, ${color} 14%, white)`, color }}>
          <i className={`ti ${icon}`} />
        </span>
        <span className="insp-section-title">{title}</span>
        <i className="ti ti-chevron-down insp-chevron" />
      </button>
      {open && <div className="insp-section-body">{children}</div>}
    </div>
  );
}

export default function Inspector({ selected, searchQuery, onViewDoc }) {
  const [insights,        setInsights]        = useState([]);
  const [insightsLoading, setInsightsLoading] = useState(false);

  const docId = selected?.doc?.id ?? selected?.hit?.document_id ?? null;

  useEffect(() => {
    if (!docId) { setInsights([]); return; }
    setInsights([]); setInsightsLoading(true);
    fetchDocumentInsights(docId)
      .then(d => setInsights(d.insights || []))
      .catch(() => setInsights([]))
      .finally(() => setInsightsLoading(false));
  }, [docId]);

  if (!selected) {
    return (
      <div className="insp-empty">
        <div className="insp-empty-icon"><i className="ti ti-layout-sidebar-right" /></div>
        <p className="insp-empty-title">No document selected</p>
        <p className="insp-empty-sub">Click any document card to inspect it here.</p>
      </div>
    );
  }

  const { doc, hit } = selected;
  const filename = doc?.filename ?? hit?.filename ?? '';
  const summary  = doc?.summary  ?? hit?.summary  ?? '';
  const tags     = doc?.tags     ?? hit?.tags      ?? [];
  const cls      = doc?.classifications ?? hit?.classifications ?? {};
  const findings = doc?.key_findings ?? hit?.key_findings ?? [];
  const docIdVal = doc?.id ?? hit?.document_id ?? null;
  const hasCls   = Object.keys(cls).some(k => cls[k]?.length > 0);
  const displayFindings = insights.length > 0 ? insights : findings;

  const ext = filename.split('.').pop()?.toLowerCase() ?? '';
  const EXT_COLOR = { pdf: 'var(--tint-red)', docx: 'var(--tint-blue)', txt: 'var(--ink3)', md: 'var(--tint-purple)' };
  const extColor = EXT_COLOR[ext] ?? 'var(--tint-blue)';

  return (
    <div className="insp-root">

      {/* ── Header ── */}
      <div className="insp-header">
        <div className="insp-file-icon" style={{ background: `color-mix(in srgb, ${extColor} 12%, white)` }}>
          <i className={`ti ${fileIcon(filename)}`} style={{ color: extColor }} />
        </div>
        <div className="insp-header-text">
          <p className="insp-filename" title={filename}>{filename}</p>
          {hit && <p className="insp-page">Page {hit.page}</p>}
          {doc?.page_count && (
            <p className="insp-page">
              {doc.page_count} page{doc.page_count !== 1 ? 's' : ''}
              {doc.file_size_bytes ? ` · ${(doc.file_size_bytes / 1024).toFixed(0)} KB` : ''}
            </p>
          )}
        </div>
        {ext && (
          <span className="insp-ext-badge"
            style={{ background: `color-mix(in srgb, ${extColor} 15%, white)`, color: extColor }}>
            .{ext.toUpperCase()}
          </span>
        )}
      </div>

      {/* ── Actions ── */}
      <div className="insp-actions">
        <button className="insp-btn insp-btn-view"
          onClick={() => onViewDoc(doc ?? { id: hit?.document_id, filename: hit?.filename })}>
          <i className="ti ti-eye" /><span>View Content</span>
        </button>
        {docIdVal && (
          <a className="insp-btn insp-btn-dl" href={downloadUrl(docIdVal)} download={filename}>
            <i className="ti ti-download" /><span>Download</span>
          </a>
        )}
      </div>

      {/* ── Sections ── */}
      <div className="insp-sections">

        {/* 1. Search match passage (only in search view) */}
        {hit && (
          <Section resetKey={docId} title="Matching Passage" icon="ti-quote" color="var(--tint-blue)" defaultOpen>
            <div className="insp-passage"
              dangerouslySetInnerHTML={{ __html: highlightText(hit.text || '', searchQuery) }} />
          </Section>
        )}

        {/* 2. AI Summary — what the paper is about */}
        <Section resetKey={docId} title="AI Summary" icon="ti-sparkles" color="var(--tint-purple)" defaultOpen={false} empty={!summary}>
          <p className="insp-summary">{summary}</p>
        </Section>

        {/* 3. Key Findings — what the paper discovered (scientific sentences) */}
        <Section resetKey={docId} title="Key Findings" icon="ti-circle-check" color="var(--tint-green)" defaultOpen={false}
          empty={!insightsLoading && displayFindings.length === 0}>
          {insightsLoading ? (
            <div className="insp-loading">
              <span className="spinner"
                style={{ borderTopColor: 'var(--tint-green)', borderColor: 'rgba(48,209,88,.15)', width: 12, height: 12 }} />
              <span>Extracting…</span>
            </div>
          ) : (
            <ul className="insp-findings">
              {displayFindings.map((f, i) => <li key={i}>{f}</li>)}
            </ul>
          )}
        </Section>

        {/* 4. Classifications — DeBERTa subject/field/doc_type/methodology */}
        {hasCls && (
          <Section resetKey={docId} title="Classifications" icon="ti-layout-grid" color="var(--tint-indigo)" defaultOpen={false}>
            <div className="insp-cls-grid">
              {Object.entries(cls).map(([dim, vals]) => {
                if (!vals?.length) return null;
                const m = DIM_META[dim] ?? { label: dim, color: 'var(--ink3)', bg: 'var(--bg2)', icon: 'ti-tag' };
                return (
                  <div key={dim} className="insp-cls-row">
                    <span className="insp-cls-dim" style={{ color: m.color }}>
                      <i className={`ti ${m.icon}`} />{m.label}
                    </span>
                    <div className="insp-cls-pills">
                      {vals.map(v => (
                        <span key={v} className="insp-cls-pill"
                          style={{ background: m.bg, color: m.color, borderColor: m.color + '33' }}>
                          {v}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </Section>
        )}

        {/* 5. Tags — YAKE keyword extraction */}
        {tags.length > 0 && (
          <Section resetKey={docId} title="Tags" icon="ti-tags" color="var(--tint-teal)" defaultOpen={false}>
            <div className="insp-tags">
              {tags.map(t => <span key={t} className="insp-tag">#{t}</span>)}
            </div>
          </Section>
        )}

        {/* 6. Entities — dates */}
        {(doc?.entities?.Dates?.length > 0 || doc?.entities?.Companies?.length > 0) && (
          <Section resetKey={docId} title="Entities" icon="ti-sitemap" color="var(--tint-pink)" defaultOpen={false}>
            <div className="insp-entities">
              {doc.entities.Companies?.length > 0 && (
                <div className="insp-entity-group">
                  <p className="insp-entity-label">Organizations</p>
                  <div className="insp-entity-chips">
                    {doc.entities.Companies.map((c, i) => <span key={i} className="entity-badge">{c}</span>)}
                  </div>
                </div>
              )}
              {doc.entities.Dates?.length > 0 && (
                <div className="insp-entity-group">
                  <p className="insp-entity-label">Dates</p>
                  <div className="insp-entity-chips">
                    {doc.entities.Dates.map((d, i) => <span key={i} className="entity-badge">{d}</span>)}
                  </div>
                </div>
              )}
            </div>
          </Section>
        )}

      </div>
    </div>
  );
}
