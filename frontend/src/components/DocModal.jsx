import { useState, useEffect } from 'react';
import { fetchDocumentText, downloadUrl } from '../lib/api.js';
import { fileIcon, highlightText } from '../lib/utils.js';

export default function DocModal({ doc, onClose, searchQuery }) {
  const [text, setText]       = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!doc) return;
    setLoading(true);
    fetchDocumentText(doc.id)
      .then(d => setText(d.text || ''))
      .catch(() => setText('Failed to load document text.'))
      .finally(() => setLoading(false));
  }, [doc]);

  if (!doc) return null;
  return (
    <div className="modal open">
      <div className="modal-backdrop" onClick={onClose} />
      <div className="modal-panel">
        <div className="modal-head">
          <h3><i className={`ti ${fileIcon(doc.filename)}`} /> {doc.filename}</h3>
          <div className="modal-actions">
            <a className="modal-dl-btn" href={downloadUrl(doc.id)} target="_blank" rel="noreferrer">
              <i className="ti ti-download" /> Download
            </a>
            <button className="modal-close" onClick={onClose}><i className="ti ti-x" /></button>
          </div>
        </div>
        <div className="modal-body">
          {loading
            ? <div style={{display:'flex',justifyContent:'center',padding:'48px'}}>
                <i className="ti ti-loader" style={{fontSize:24,color:'var(--accent)',animation:'spin .7s linear infinite'}} />
              </div>
            : <div className="modal-text"
                dangerouslySetInnerHTML={{__html: highlightText(text, searchQuery)}} />
          }
        </div>
      </div>
    </div>
  );
}
