import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  fetchDocuments, fetchTags, fetchCounts, fetchPerspectives,
  uploadFile, searchDocuments, deleteDocument, fetchDocumentStatus,
  downloadUrl, fetchTagsConfig
} from './lib/api.js';
import { escapeHtml, highlightText, fileIcon } from './lib/utils.js';

import Toast             from './components/Toast.jsx';
import DocModal          from './components/DocModal.jsx';
import UploadSheet       from './components/UploadSheet.jsx';
import FileItem          from './components/FileItem.jsx';
import Inspector         from './components/Inspector.jsx';
import PerspectiveColumn from './components/PerspectiveColumn.jsx';

// ── Main App ─────────────────────────────────────────────────────────────────
// Dynamic config is now loaded from the backend via fetchTagsConfig()

function TagClsSection({ cls, pm, activeTag, selectTag }) {
  const [open, setOpen] = React.useState(false);
  const chipBg = pm.dimColor;
  const chipColor = pm.color;
  return (
    <div className="tag-hier-cls">
      <button className="tag-hier-cls-head" onClick={() => setOpen(o => !o)}>
        <i className={`ti ti-chevron-right tag-cls-chevron${open ? ' open' : ''}`} />
        <span>{cls.name}</span>
        <span className="tag-hier-cls-count" style={{ background: chipBg, color: chipColor }}>
          {cls.tags.length} tags
        </span>
      </button>
      {open && (
        <div className="tag-hier-chips tag-chips-animate">
          {cls.tags.map((tag, i) => (
            <div
              key={tag.name}
              className={`tag-chip${activeTag === tag.name ? ' active' : ''}`}
              style={{
                '--chip-bg': chipBg,
                '--chip-color': chipColor,
                '--chip-delay': `${i * 18}ms`,
              }}
              onClick={() => selectTag(tag.name)}
              title={`${tag.count} doc${tag.count !== 1 ? 's' : ''}`}
            >
              <span className="tag-chip-hash">#</span>{tag.name}
              <span className="tag-chip-count">{tag.count}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TagHierarchyView({ tagsHierarchy, tagsConfig, activeTag, selectTag }) {
  const initCollapsed = tagsHierarchy.reduce((a, p) => ({ ...a, [p.key]: true }), {});
  const [collapsedPersp, setCollapsedPersp] = React.useState(initCollapsed);
  const togglePersp = key => setCollapsedPersp(s => ({ ...s, [key]: !s[key] }));
  return (
    <div className="tag-hierarchy">
      {tagsHierarchy.map(perspective => {
        const pm = tagsConfig[perspective.key] || { icon: 'ti-layers', color: '#b09060', dimColor: '#f5f0e6', chipColors: [] };
        const collapsed = collapsedPersp[perspective.key];
        const totalTags = perspective.classifications.reduce((a, c) => a + c.tags.length, 0);
        return (
          <div key={perspective.key} className={`tag-hier-perspective${collapsed ? ' collapsed' : ''}`}
            style={{ '--persp-color': pm.color, '--persp-dim': pm.dimColor }}>
            <button className="tag-hier-persp-head" onClick={() => togglePersp(perspective.key)}>
              <span className="persp-icon-wrap" style={{ background: pm.dimColor }}>
                <i className={`ti ${pm.icon}`} style={{ color: pm.color }} />
              </span>
              <span className="persp-label">{perspective.label}</span>
              <span className="persp-stats">
                <span className="persp-stat-pill" style={{ background: pm.dimColor, color: pm.color }}>
                  {perspective.classifications.length} categories
                </span>
                <span className="persp-stat-pill" style={{ background: pm.dimColor, color: pm.color }}>
                  {totalTags} tags
                </span>
              </span>
              <i className={`ti ti-chevron-down persp-chevron${collapsed ? '' : ' open'}`} />
            </button>
            {!collapsed && (
              <div className="tag-hier-body">
                {perspective.classifications.map(cls => (
                  <TagClsSection key={cls.name} cls={cls} pm={pm} activeTag={activeTag} selectTag={selectTag} />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function App() {
  // ── State ──────────────────────────────────────────────────────────────────
  const [view,   setView]   = useState('lib');   // lib | search | tags
  const [docs,   setDocs]   = useState([]);
  const [counts, setCounts] = useState({ all: 0, processing: 0, failed: 0 });

  const [tagsFlat,      setTagsFlat]      = useState([]);
  const [tagsHierarchy, setTagsHierarchy] = useState([]);   // [{key,label,classifications:[{name,tags}]}]
  const [perspectives,  setPerspectives]  = useState([]);   // [{key,label,items}]
  const [tagsConfig,    setTagsConfig]    = useState({});   // dynamic taxonomy dimensions

  const [activeClassification, setActiveClassification] = useState(null); // {dimension, value}
  const [activeTag,            setActiveTag]            = useState(null); // keyword tag filter

  const [selected,     setSelected]     = useState(null);   // {doc} | {hit}
  const [searchQuery,  setSearchQuery]  = useState('');
  const [searchHits,   setSearchHits]   = useState([]);
  const [searching,    setSearching]    = useState(false);

  const [uploadOpen,    setUploadOpen]    = useState(false);
  const [toast,         setToast]         = useState({ msg: '', spinner: false });
  const [modalDoc,      setModalDoc]      = useState(null);
  const [progress,      setProgress]      = useState({});
  const [progressPollers, setProgressPollers] = useState({});
  const [sidebarOpen,   setSidebarOpen]   = useState(true);
  const [filesOpen,     setFilesOpen]     = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(true);

  const pollingRef     = useRef(null);
  const searchInputRef = useRef();

  // ── Toast helpers ───────────────────────────────────────────────────────────
  const showToast = useCallback((msg, spinner = false) => {
    setToast({ msg, spinner });
    if (!spinner) setTimeout(() => setToast({ msg: '', spinner: false }), 3000);
  }, []);
  const hideToast = useCallback(() => setToast({ msg: '', spinner: false }), []);

  // ── Data loaders ────────────────────────────────────────────────────────────
  const loadDocs = useCallback(async () => {
    try {
      const dim  = activeClassification?.dimension || null;
      const val  = activeClassification?.value     || null;
      const data = await fetchDocuments(null, activeTag, dim, val);
      setDocs(data);
      if (!data.some(d => d.status === 'processing') && pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
        hideToast();
      }
    } catch (e) { console.error(e); }
  }, [activeClassification, activeTag, hideToast]);

  const loadMeta = useCallback(async () => {
    try {
      const [tagData, perspData, configData] = await Promise.all([fetchTags(), fetchPerspectives(), fetchTagsConfig()]);
      // tagData shape: {hierarchy: [...], flat: [...]}
      setTagsFlat(tagData.flat      || []);
      setTagsHierarchy(tagData.hierarchy || []);
      setPerspectives(Array.isArray(perspData) ? perspData : []);
      setTagsConfig(configData || {});
    } catch (e) { console.error(e); }
  }, []);

  const loadCounts = useCallback(async () => {
    try { setCounts(await fetchCounts()); } catch {}
  }, []);

  const startPolling = useCallback(() => {
    if (pollingRef.current) return;
    pollingRef.current = setInterval(() => { loadDocs(); loadMeta(); loadCounts(); }, 5000);
  }, [loadDocs, loadMeta, loadCounts]);

  useEffect(() => {
    loadDocs(); loadMeta(); loadCounts(); startPolling();
    return () => { if (pollingRef.current) clearInterval(pollingRef.current); };
  }, []);

  useEffect(() => { loadDocs(); }, [activeClassification, activeTag]);

  // ── Per-doc progress polling ────────────────────────────────────────────────
  const startProgressPolling = useCallback((docId) => {
    setProgressPollers(prev => {
      if (prev[docId]) return prev;
      const id = setInterval(async () => {
        try {
          const data = await fetchDocumentStatus(docId);
          setProgress(p => ({ ...p, [docId]: data }));
          if (data.status !== 'processing') {
            clearInterval(id);
            setProgressPollers(pp => { const n = { ...pp }; delete n[docId]; return n; });
            setProgress(p => { const n = { ...p }; delete n[docId]; return n; });
            await loadDocs(); await loadMeta(); await loadCounts();
          }
        } catch {}
      }, 2500);
      return { ...prev, [docId]: id };
    });
  }, [loadDocs, loadMeta]);

  // ── Upload ──────────────────────────────────────────────────────────────────
  const handleUpload = async (files) => {
    if (!files?.length) return;
    showToast(`Uploading ${files.length > 1 ? `${files.length} files` : files[0].name}…`, true);
    for (const file of Array.from(files)) {
      try {
        const resp = await uploadFile(file);
        if (resp.document_id) {
          setProgress(p => ({ ...p, [resp.document_id]: { step: 'queued', pct: 0, detail: 'Starting…', status: 'processing' } }));
          startProgressPolling(resp.document_id);
        }
        showToast(`Processing: ${file.name}`, true);
      } catch (e) {
        showToast(`Error: ${e.message}`);
      }
    }
    setUploadOpen(false);
    loadDocs(); startPolling();
  };

  // ── Delete ──────────────────────────────────────────────────────────────────
  const handleDelete = async (docId, e) => {
    e.stopPropagation();
    if (!confirm('Delete this document and clear its index?')) return;
    showToast('Deleting…', true);
    try {
      await deleteDocument(docId);
      showToast('Deleted.');
      if (selected?.doc?.id === docId || selected?.hit?.document_id === docId) setSelected(null);
      loadDocs(); loadMeta(); loadCounts();
    } catch (err) { showToast(`Delete failed: ${err.message}`); }
  };

  // ── Search ──────────────────────────────────────────────────────────────────
  const handleSearch = async () => {
    const q = searchInputRef.current?.value.trim();
    if (!q) return;
    setSearchQuery(q); setSearching(true); setView('search'); setSearchHits([]);
    try { setSearchHits(await searchDocuments(q, 10)); }
    catch (e) { showToast(`Search failed: ${e.message}`); }
    finally { setSearching(false); }
  };

  // ── View / filter helpers ───────────────────────────────────────────────────
  const handleSetView = (v) => {
    setView(v);
    if (v === 'search') setTimeout(() => searchInputRef.current?.focus(), 80);
  };

  const selectClassification = (cls) => {
    setActiveClassification(cls);
    setActiveTag(null);
    setView('lib');
  };

  const selectTag = (name) => {
    setActiveTag(t => t === name ? null : name);
    setActiveClassification(null);
    setView('lib');
  };

  // ── Derived values ──────────────────────────────────────────────────────────
  const completed = docs.filter(d => d.status === 'completed');

  const topbarTitle = view === 'search'
    ? <><em>Search</em></>
    : view === 'tags'
    ? <>Tag <em>directory</em></>
    : <>Your <em>library</em></>;

  const activeFilterPill = view === 'lib' && (activeClassification || activeTag)
    ? (
      <div className="active-filter-pill">
        <i className={`ti ${activeClassification ? 'ti-atom' : 'ti-tag'}`} />
        <span>{activeClassification ? activeClassification.value : `#${activeTag}`}</span>
        <button onClick={() => { setActiveClassification(null); setActiveTag(null); }} title="Clear filter">
          <i className="ti ti-x" />
        </button>
      </div>
    ) : null;

  const resultsLabel = view === 'search'
    ? (searching ? 'Searching…' : `${searchHits.length} results`)
    : `${completed.length} docs`;

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <>
      <div className="app-root">

        {/* ── Rail ─────────────────────────────────────────────────────── */}
        <div className="rail">
          <div className="rail-logo" title="DocuSync"><i className="ti ti-files" /></div>

          {/* Sidebar toggle */}
          <div className={`rail-item${sidebarOpen ? ' active' : ''}`}
            onClick={() => setSidebarOpen(o => !o)} title="Toggle Sidebar">
            <i className="ti ti-layout-sidebar" /><span>Panel</span>
          </div>

          <div className="rail-divider" />

          {[
            { id:'lib',    icon:'ti-layout-list', label:'Library' },
            { id:'search', icon:'ti-search',       label:'Search'  },
            { id:'tags',   icon:'ti-tag',          label:'Tags'    },
          ].map(r => (
            <div key={r.id} className={`rail-item${view === r.id ? ' active' : ''}`}
              onClick={() => handleSetView(r.id)} title={r.label}>
              <i className={`ti ${r.icon}`} /><span>{r.label}</span>
            </div>
          ))}
          <div className="rail-item" onClick={() => setUploadOpen(true)} title="Upload">
            <i className="ti ti-upload" /><span>Upload</span>
          </div>
          <div className="rail-bottom">
            <div className={`rail-item${inspectorOpen ? ' active' : ''}`}
              onClick={() => setInspectorOpen(o => !o)} title="Toggle Inspector">
              <i className="ti ti-layout-sidebar-right" /><span>Info</span>
            </div>
          </div>
        </div>

        {/* ── Sidebar ──────────────────────────────────────────────────── */}
        <aside className={`sidebar${sidebarOpen ? '' : ' collapsed'}`}>
          <div className="sidebar-inner">
            <div className="sb-logo">Docu<em>Sync</em></div>

            {/* All Documents */}
            <div className="lib-type-nav">
              <span className="lib-section-label">Library</span>
              <div
                className={`lib-type-item${!activeClassification && !activeTag && view === 'lib' ? ' active' : ''}`}
                onClick={() => { setActiveClassification(null); setActiveTag(null); setView('lib'); }}>
                <i className="ti ti-layers" /> All Documents
                <span className="lib-type-badge">{counts.all}</span>
              </div>
            </div>

            {/* Perspective columns — each individually collapsible */}
            {perspectives.map(p => (
              <PerspectiveColumn
                key={p.key}
                perspective={p}
                tagsConfig={tagsConfig}
                activeClassification={activeClassification}
                onSelect={selectClassification}
              />
            ))}
            {perspectives.length === 0 && counts.all > 0 && (
              <div style={{ padding:'10px 8px', color:'var(--ink4)', fontSize:11 }}>
                Classifications loading…
              </div>
            )}

            {/* Recent documents — collapsible, max 20 */}
            <div className="sb-section">
              <button className="sb-section-hd" onClick={() => setFilesOpen(o => !o)}>
                <span className="sb-section-lbl"><i className="ti ti-clock" /> Recent</span>
                <i className={`ti ti-chevron-right sb-chevron${filesOpen ? ' open' : ''}`} />
              </button>
              {filesOpen && (
                <div className="sb-section-body">
                  <div className="file-list">
                    {docs.length === 0
                      ? <p className="empty-state">No documents yet.</p>
                      : docs.map(doc => (
                          <FileItem key={doc.id} doc={doc} progress={progress[doc.id]}
                            onDelete={handleDelete}
                            onView={(id, fname) => setModalDoc({ id, filename: fname })} />
                        ))
                    }
                  </div>
                </div>
              )}
            </div>

            {/* Stats */}
            <div className="sb-stats">
              <div className="stat-pill stat-pill-indexed">
                <span className="stat-n">{counts.all}</span>
                <span className="stat-l">Indexed</span>
              </div>
              <div className="stat-pill stat-pill-queued">
                <span className="stat-n">{counts.processing}</span>
                <span className="stat-l">Queued</span>
              </div>
              <div className="stat-pill stat-pill-failed">
                <span className="stat-n">{counts.failed}</span>
                <span className="stat-l">Failed</span>
              </div>
            </div>
          </div>
        </aside>

        {/* ── Main Workspace ────────────────────────────────────────────── */}
        <main className="main-workspace">
          <header className="topbar">
            <div className="topbar-left">
              <h1 className="topbar-title">{topbarTitle}</h1>
              {activeFilterPill}
            </div>
            <div className="topbar-right">
              <div className="search-wrap">
                <i className="ti ti-search search-icon-inner" />
                <input ref={searchInputRef} type="text"
                  placeholder="Search by meaning, keyword, or tag…"
                  autoComplete="off"
                  onKeyDown={e => e.key === 'Enter' && handleSearch()} />
                <button className="search-btn" onClick={handleSearch}>Search</button>
              </div>
              <button className="upload-pill" onClick={() => setUploadOpen(true)}>
                <i className="ti ti-upload" /> Upload
              </button>
            </div>
          </header>

          <div className="workspace-split">
            {/* Results column */}
            <section className="col-results">
              <div className="col-header">
                <span className="col-title"><i className="ti ti-list-search" /> Results</span>
                <span className="col-badge">{resultsLabel}</span>
              </div>
              <div className="results-list">

                {view === 'tags' ? (
                  /* ── Tag directory — hierarchy view ── */
                  tagsHierarchy.length ? (
                    <TagHierarchyView
                      tagsHierarchy={tagsHierarchy}
                      tagsConfig={tagsConfig}
                      activeTag={activeTag}
                      selectTag={selectTag}
                    />
                  ) : (
                    <div className="empty-card">
                      <i className="ti ti-tags empty-icon" />
                      <p className="empty-title">No tags yet</p>
                      <p className="empty-sub">Upload documents to generate keyword tags automatically.</p>
                    </div>
                  )

                ) : view === 'search' ? (
                  /* ── Search results ── */
                  searching ? (
                    <div className="empty-card">
                      <i className="ti ti-loader empty-icon" style={{ animation:'spin .7s linear infinite' }} />
                      <p className="empty-title">Searching vector store…</p>
                    </div>
                  ) : searchHits.length === 0 ? (
                    <div className="empty-card">
                      <i className="ti ti-search empty-icon" />
                      <p className="empty-title">Search your documents</p>
                      <p className="empty-sub">Use the bar above to search by meaning, keyword, or paste a question.</p>
                    </div>
                  ) : (
                    searchHits.map((hit, idx) => {
                      const relevancy = Math.round((hit.similarity || 0) * 100);
                      const tagsHtml  = (hit.tags || []).slice(0, 3).map(t => `<span class="result-tag-badge">#${t}</span>`).join(' ');
                      return (
                        <div key={idx} className={`result-card${selected?.hit === hit ? ' active' : ''}`}
                          style={{ '--card-index': idx }}
                          onClick={() => { setSelected({ hit }); setInspectorOpen(true); }}>
                          <div className="result-header">
                            <div className="result-doc-name">
                              <i className={`ti ${fileIcon(hit.filename)}`} />
                              <span>{hit.filename}</span>
                            </div>
                            <div className="result-meta">
                              <span className="result-score">{relevancy}% Match</span>
                              <span className="result-page">Page {hit.page}</span>
                            </div>
                          </div>
                          <div className="result-snippet"
                            dangerouslySetInnerHTML={{ __html: `"…${highlightText(hit.text || '', searchQuery)}…"` }} />
                          <div className="result-tags" dangerouslySetInnerHTML={{ __html: tagsHtml }} />
                        </div>
                      );
                    })
                  )

                ) : (
                  /* ── Library view ── */
                  completed.length === 0 ? (
                    <div className="empty-card">
                      <i className="ti ti-inbox empty-icon" />
                      <p className="empty-title">No documents</p>
                      <p className="empty-sub">Upload a PDF, DOCX or TXT to get started — AI tagging runs automatically.</p>
                    </div>
                  ) : (
                    completed.map((doc, idx) => {
                      const cls        = doc.classifications || {};
                      const subjects   = cls.subject      || [];
                      const methodology= cls.methodology  || [];
                      const docType    = (cls.doc_type    || [])[0] || '';
                      const tags       = doc.tags         || [];

                      // Pills: subjects (blue) + methodology (orange)
                      const subjHtml = subjects.slice(0, 2).map(s =>
                        `<span class="result-cls-badge">${escapeHtml(s)}</span>`).join('');
                      const methHtml = methodology.slice(0, 1).map(m =>
                        `<span class="result-cls-badge result-cls-meth">${escapeHtml(m)}</span>`).join('');
                      const pillsHtml = subjHtml + methHtml ||
                        tags.slice(0, 2).map(t => `<span class="result-tag-badge">#${escapeHtml(t)}</span>`).join('');

                      const dtHtml   = docType ? `<span class="result-doctype-badge">${escapeHtml(docType)}</span>` : '';
                      const tagsHtml = tags.slice(0, 3).map(t => `<span class="result-tag-badge">#${escapeHtml(t)}</span>`).join(' ');
                      const rawSum   = (doc.summary || '').replace(/\s+/g, ' ').trim();
                      const summary  = rawSum.toLowerCase().includes('scifact') ? '' : rawSum;
                      const sizeKb   = doc.file_size_bytes ? (doc.file_size_bytes / 1024).toFixed(1) + ' KB' : '';
                      const pages    = doc.page_count ? `${doc.page_count} pg${doc.page_count !== 1 ? 's' : ''}` : '';
                      const meta     = [pages, sizeKb].filter(Boolean).join(' · ');

                      return (
                        <div key={doc.id} className={`result-card${selected?.doc?.id === doc.id ? ' active' : ''}`}
                          style={{ '--card-index': idx }}
                          onClick={() => { setSelected({ doc }); setInspectorOpen(true); }}>
                          <div className="result-header">
                            <div className="result-doc-name">
                              <i className={`ti ${fileIcon(doc.filename)}`} />
                              <span>{doc.filename}</span>
                            </div>
                            <div className="result-meta">
                              {dtHtml && <span dangerouslySetInnerHTML={{ __html: dtHtml }} />}
                              {meta && <span className="result-page">{meta}</span>}
                            </div>
                          </div>
                          {pillsHtml && <div className="result-cls-row" dangerouslySetInnerHTML={{ __html: pillsHtml }} />}
                          {summary && <div className="result-snippet">{summary}</div>}
                          {tagsHtml && <div className="result-tags" dangerouslySetInnerHTML={{ __html: tagsHtml }} />}
                        </div>
                      );
                    })
                  )
                )}

              </div>
            </section>

            {/* Inspector column */}
            <section className={`col-inspector${inspectorOpen ? '' : ' collapsed'}`}>
              <button className="insp-collapse-btn" onClick={() => setInspectorOpen(false)}
                title="Collapse panel" aria-label="Collapse inspector">
                <i className="ti ti-layout-sidebar-right-collapse" />
              </button>
              <Inspector selected={selected} searchQuery={searchQuery} onViewDoc={setModalDoc} />
            </section>
          </div>
        </main>
      </div>

      {/* ── Overlays ── */}
      <UploadSheet open={uploadOpen} onClose={() => setUploadOpen(false)} onFilesSelected={handleUpload} />
      <Toast msg={toast.msg} spinner={toast.spinner} />
      <DocModal doc={modalDoc} onClose={() => setModalDoc(null)} searchQuery={searchQuery} />
    </>
  );
}
