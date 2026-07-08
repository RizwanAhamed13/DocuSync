import { downloadUrl } from '../lib/api.js';
import { fileIcon } from '../lib/utils.js';

const STEP_LABELS = {
  queued:'Queued', parsing:'Parsing', ai_tagging:'AI Analysis',
  chunking:'Chunking', embedding:'Embedding', saving:'Saving',
  completed:'Complete', failed:'Failed',
};
const STEP_ICONS = {
  queued:'ti-clock', parsing:'ti-file-text', ai_tagging:'ti-sparkles',
  chunking:'ti-scissors', embedding:'ti-brain', saving:'ti-database',
  completed:'ti-circle-check', failed:'ti-circle-x',
};
const STEP_ETA = {
  queued:'~45s', parsing:'~40s', ai_tagging:'~35s',
  chunking:'~8s', embedding:'~5s', saving:'~2s',
};

export default function FileItem({ doc, progress, onDelete, onView }) {
  const icon = fileIcon(doc.filename);

  if (doc.status === 'processing') {
    const prog = progress || {};
    const pct  = prog.pct  || 0;
    const step = prog.step || 'queued';
    return (
      <div className="file-item file-item-processing">
        <div className="file-header-row">
          <div className="file-info">
            <i className={`ti ${icon} file-icon-pulse`} style={{ color: 'var(--accent)' }} />
            <div className="file-text">
              <div className="file-name" title={doc.filename}>{doc.filename}</div>
              <span style={{ fontSize: 10, color: 'var(--ink4)' }}>
                Processing · ETA {STEP_ETA[step] || '…'}
              </span>
            </div>
          </div>
          <button className="btn-delete-file" onClick={e => onDelete(doc.id, e)} title="Cancel & Delete">
            <i className="ti ti-trash" />
          </button>
        </div>
        <div className="ingest-progress-wrap">
          <div className="progress-header-row">
            <span className="progress-step-label">
              <i className={`ti ${STEP_ICONS[step] || 'ti-settings'}`} /> {STEP_LABELS[step] || step}
            </span>
            <span className="progress-pct-badge">{pct}%</span>
          </div>
          <div className="progress-bar-track">
            <div className="progress-bar-fill" style={{ width: `${Math.max(pct, 4)}%` }} />
          </div>
          <div className="progress-detail-text">{prog.detail || ''}</div>
        </div>
      </div>
    );
  }

  if (doc.status === 'failed') {
    const errShort = (doc.error_message || 'Unknown error').slice(0, 60);
    return (
      <div className="file-item">
        <div className="file-info" style={{ width:'100%', flexDirection:'column', gap:4, alignItems:'flex-start' }}>
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', width:'100%' }}>
            <div style={{ display:'flex', alignItems:'center', gap:8 }}>
              <i className={`ti ${icon}`} style={{ color: 'var(--red)' }} />
              <div className="file-name">{doc.filename}</div>
            </div>
            <div style={{ display:'flex', alignItems:'center', gap:4 }}>
              <span className="file-status-badge status-failed">Failed</span>
              <button className="btn-delete-file" onClick={e => onDelete(doc.id, e)}>
                <i className="ti ti-trash" />
              </button>
            </div>
          </div>
          <span style={{ fontSize:10, color:'var(--red)', paddingLeft:24 }}>{errShort}</span>
        </div>
      </div>
    );
  }

  const sizeKb      = doc.file_size_bytes ? (doc.file_size_bytes / 1024).toFixed(1) + ' KB' : '';
  const pages       = doc.page_count ? `${doc.page_count} pg${doc.page_count !== 1 ? 's' : ''}` : '';
  const meta        = [pages, sizeKb].filter(Boolean).join(' · ');
  const summary     = (doc.summary || '').replace(/\s+/g, ' ').trim();
  const shortSummary = summary.length > 80 ? summary.slice(0, 78) + '…' : summary;

  return (
    <div className="file-item" style={{ cursor: 'pointer' }} onClick={() => onView(doc.id, doc.filename)}>
      <div className="file-info" style={{ minWidth: 0, flex: 1 }}>
        <i className={`ti ${icon}`} style={{ color: 'var(--accent)', flexShrink: 0 }} />
        <div className="file-text" style={{ minWidth: 0 }}>
          <div className="file-name" title={doc.filename}>{doc.filename}</div>
          {shortSummary
            ? <span style={{ fontSize:10, color:'var(--ink4)', display:'block', whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }} title={summary}>{shortSummary}</span>
            : <span style={{ fontSize:10, color:'var(--ink4)' }}>{meta}</span>
          }
        </div>
      </div>
      <div style={{ display:'flex', alignItems:'center', gap:4, flexShrink:0 }}>
        <a className="btn-delete-file" href={downloadUrl(doc.id)} target="_blank" rel="noreferrer"
           onClick={e => e.stopPropagation()} title="Download"
           style={{ color:'var(--ink4)', textDecoration:'none' }}>
          <i className="ti ti-file-arrow-down" />
        </a>
        <button className="btn-delete-file" onClick={e => onDelete(doc.id, e)} title="Delete">
          <i className="ti ti-trash" />
        </button>
      </div>
    </div>
  );
}
