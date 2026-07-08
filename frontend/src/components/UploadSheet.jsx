import { useState, useRef, useCallback } from 'react';

export default function UploadSheet({ open, onClose, onFilesSelected }) {
  const [dragging, setDragging] = useState(false);
  const [queued,   setQueued]   = useState([]);
  const inputRef = useRef();

  const addFiles = useCallback((fileList) => {
    const arr = Array.from(fileList).filter(f =>
      /\.(pdf|docx|txt|md)$/i.test(f.name)
    );
    setQueued(prev => {
      const names = new Set(prev.map(f => f.name));
      return [...prev, ...arr.filter(f => !names.has(f.name))];
    });
  }, []);

  const remove = (name) => setQueued(q => q.filter(f => f.name !== name));

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    addFiles(e.dataTransfer.files);
  };

  const handleSubmit = () => {
    if (!queued.length) return;
    // Pass the File[] directly — handleUpload uses Array.from(), so no
    // DataTransfer/FileList reconstruction needed (that was flaky across browsers).
    onFilesSelected(queued);
    setQueued([]);
  };

  const fmt = (bytes) => bytes < 1024 * 1024
    ? `${(bytes / 1024).toFixed(0)} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;

  return (
    <div className={`upload-sheet${open ? ' open' : ''}`} aria-hidden={!open}>
      <div className="upload-sheet-backdrop" onClick={onClose} />
      <div className="upload-sheet-panel">
        {/* Header */}
        <div className="us-head">
          <div>
            <p className="us-title">Upload documents</p>
            <p className="us-sub">PDF, DOCX, TXT · up to 120 MB · AI tagging auto-runs</p>
          </div>
          <button className="us-close" onClick={onClose} aria-label="Close">
            <i className="ti ti-x" />
          </button>
        </div>

        {/* Drop zone */}
        <div
          className={`dropzone${dragging ? ' dragover' : ''}`}
          onDragOver={e => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
        >
          <input
            id="docusync-file-input"
            ref={inputRef}
            type="file"
            multiple
            accept=".pdf,.docx,.txt,.md"
            style={{ display: 'none' }}
            onChange={e => { addFiles(e.target.files); e.target.value = ''; }}
          />
          {/* The whole inner area is a <label> — clicking anywhere natively opens the picker */}
          <label htmlFor="docusync-file-input" className="dz-inner" style={{ cursor: 'pointer' }}>
            <div className="dz-icon">
              <i className={`ti ${dragging ? 'ti-arrows-down' : 'ti-cloud-upload'}`} />
            </div>
            <p className="dz-title">{dragging ? 'Drop to add' : 'Drag files here'}</p>
            <p className="dz-sub">or click to browse</p>
            <span className="dz-btn">
              <i className="ti ti-folder-open" /> Browse files
            </span>
          </label>
        </div>

        {/* File queue */}
        {queued.length > 0 && (
          <div className="us-queue">
            {queued.map(f => (
              <div key={f.name} className="us-queue-item">
                <i className="ti ti-file-text" style={{ color:'var(--tint-blue)', fontSize:15, flexShrink:0 }} />
                <span className="us-queue-name">{f.name}</span>
                <span className="us-queue-size">{fmt(f.size)}</span>
                <button className="us-queue-rm" onClick={() => remove(f.name)} title="Remove">
                  <i className="ti ti-x" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Submit */}
        <button
          className={`us-submit${queued.length ? '' : ' disabled'}`}
          disabled={!queued.length}
          onClick={handleSubmit}
        >
          <i className="ti ti-upload" />
          {queued.length ? `Upload ${queued.length} file${queued.length > 1 ? 's' : ''}` : 'Select files to upload'}
        </button>
      </div>
    </div>
  );
}
