import { useState, useRef, useEffect } from "react";
import { Upload, X, CheckCircle, AlertCircle, RefreshCw } from "lucide-react";
import { apiFetch, endpoints } from "../lib/api";

const STEP_LABELS = {
  queued: 'Queued',
  parsing: 'Parsing Pages',
  ai_tagging: 'AI Analysis',
  chunking: 'Splitting Chunks',
  embedding: 'Generating Vectors',
  saving: 'Persisting Index',
  completed: 'Complete',
  failed: 'Failed',
};

const STEP_ETA = {
  queued: '~45s',
  parsing: '~40s',
  ai_tagging: '~35s',
  chunking: '~8s',
  embedding: '~5s',
  saving: '~2s',
};

const UploadFile = () => {
  const [selectedFile, setSelectedFile] = useState(null);
  const [status, setStatus] = useState("idle"); // idle, uploading, success, error
  const [message, setMessage] = useState("");
  const [activePollers, setActivePollers] = useState({}); // docId -> setInterval id
  const [processingDocs, setProcessingDocs] = useState([]); // list of docs being ingested: { id, filename, step, pct, detail, status }

  const fileInputRef = useRef(null);

  const ALLOWED_EXTENSIONS = /\.(pdf|docx|txt|md|json)$/i;

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (!ALLOWED_EXTENSIONS.test(file.name)) {
      setStatus("error");
      setMessage("Invalid file format. Allowed formats: PDF, DOCX, TXT, MD, JSON");
      setSelectedFile(null);
      return;
    }

    setStatus("idle");
    setMessage("");
    setSelectedFile(file);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.currentTarget.classList.add("border-blue-500", "bg-blue-50/10");
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.currentTarget.classList.remove("border-blue-500", "bg-blue-50/10");
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.currentTarget.classList.remove("border-blue-500", "bg-blue-50/10");
    const file = e.dataTransfer.files[0];
    if (!file) return;

    if (!ALLOWED_EXTENSIONS.test(file.name)) {
      setStatus("error");
      setMessage("Invalid file format. Allowed formats: PDF, DOCX, TXT, MD, JSON");
      setSelectedFile(null);
      return;
    }

    setStatus("idle");
    setMessage("");
    setSelectedFile(file);
  };

  const startProgressPolling = (docId, filename) => {
    // Add to processingDocs
    setProcessingDocs(prev => {
      if (prev.some(d => d.id === docId)) return prev;
      return [...prev, { id: docId, filename, step: 'queued', pct: 0, detail: 'Waiting to start…', status: 'processing' }];
    });

    const interval = setInterval(async () => {
      try {
        const data = await apiFetch(endpoints.documents.status(docId));
        
        // Update document state
        setProcessingDocs(prev => 
          prev.map(d => d.id === docId ? { ...d, ...data } : d)
        );

        if (data.status !== 'processing') {
          clearInterval(interval);
          setActivePollers(prev => {
            const copy = { ...prev };
            delete copy[docId];
            return copy;
          });
        }
      } catch (err) {
        console.error(`Error polling status for ${docId}:`, err);
      }
    }, 2500);

    setActivePollers(prev => ({ ...prev, [docId]: interval }));
  };

  // Clean up pollers on unmount
  useEffect(() => {
    return () => {
      Object.values(activePollers).forEach(clearInterval);
    };
  }, [activePollers]);

  const handleUpload = async () => {
    if (!selectedFile) {
      setStatus("error");
      setMessage("Please select or drop a document first.");
      return;
    }

    setStatus("uploading");
    setMessage(`Uploading "${selectedFile.name}"...`);

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const response = await apiFetch(endpoints.documents.upload, {
        method: "POST",
        body: formData,
      });

      const docId = response.document_id;
      
      setStatus("success");
      setMessage("Document Accepted! Background AI extraction started.");

      if (docId) {
        startProgressPolling(docId, selectedFile.name);
      }

      // Reset dropzone file state
      setTimeout(() => {
        setSelectedFile(null);
        setStatus("idle");
        setMessage("");
      }, 3500);

    } catch (err) {
      console.error(err);
      setStatus("error");
      setMessage(err.message || "Upload failed. Please check your network or server logs.");
    }
  };

  const handleCancel = () => {
    setSelectedFile(null);
    setStatus("idle");
    setMessage("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const sizeKb = (bytes) => (bytes / 1024).toFixed(1);

  return (
    <div className="bg-surface text-on-surface font-body h-full w-full flex items-center justify-center overflow-y-auto">
      <div className="max-w-5xl w-full space-y-8">
        
        {/* Upload Card */}
        <div className="bg-white rounded-[2rem] shadow-[0_20px_50px_rgba(11,28,48,0.05)] border border-slate-100 px-8 md:px-12 py-8 md:py-12 relative overflow-hidden group transition-all duration-500">
          <div className="absolute -top-24 -right-24 w-64 h-64 bg-blue-50/40 rounded-full blur-3xl pointer-events-none"></div>
          
          <div className="relative z-10">
            <div className="mb-8 text-center">
              <h2 className="font-headline text-3xl font-bold text-slate-800 tracking-tight mb-2">
                Upload Digital Asset
              </h2>
              <p className="font-body text-slate-500 text-base">
                Add PDF, DOCX, TXT, MD or JSON files to feed the local vector search engine.
              </p>

              {status !== "idle" && (
                <div className={`mt-6 p-4 rounded-xl text-base font-semibold transition-all duration-300 animate-in fade-in zoom-in-95 ${
                  status === "success" ? "bg-emerald-50 text-emerald-700 border border-emerald-100" :
                  status === "error" ? "bg-red-50 text-red-700 border border-red-100" :
                  "bg-blue-50 text-blue-700 border border-blue-100"
                }`}>
                  <div className="flex items-center justify-center gap-2.5">
                    {status === "success" && <CheckCircle className="h-5 w-5 text-emerald-500" />}
                    {status === "error" && <AlertCircle className="h-5 w-5 text-red-500" />}
                    {status === "uploading" && <RefreshCw className="h-5 w-5 text-blue-500 animate-spin" />}
                    <span>{message}</span>
                  </div>
                </div>
              )}
            </div>

            <form className="space-y-6" onSubmit={(e) => e.preventDefault()}>
              {/* Drag and Drop Zone */}
              <div 
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                className="relative flex flex-col items-center justify-center py-20 px-8 bg-slate-50/50 rounded-[1.5rem] border-2 border-dashed border-slate-200 hover:bg-blue-50/10 hover:border-blue-400 transition-all duration-300 cursor-pointer group/dropzone overflow-hidden"
              >
                <div className="relative flex flex-col items-center text-center">
                  <div className="mb-6 p-4 bg-white rounded-[1.25rem] text-blue-600 shadow-sm border border-slate-100 transition-all duration-300 group-hover/dropzone:scale-110 group-hover/dropzone:shadow-md">
                    <Upload className="h-9 w-9" />
                  </div>
                  <h3 className="font-headline font-bold text-lg text-slate-800 mb-2">
                    {selectedFile ? selectedFile.name : "Select Document"}
                  </h3>
                  <p className="font-body text-sm text-slate-400 max-w-[380px] mb-6">
                    {selectedFile 
                      ? `${sizeKb(selectedFile.size)} KB · Click Upload Asset to begin`
                      : "Drag & drop your files here, or click to browse"
                    }
                  </p>

                  <div className="flex items-center gap-3">
                    {['PDF', 'DOCX', 'TXT', 'MD', 'JSON'].map(ext => (
                      <span key={ext} className="flex items-center px-4 py-1.5 bg-white text-slate-500 text-[11px] font-bold rounded-full border border-slate-200 uppercase tracking-wider">
                        {ext}
                      </span>
                    ))}
                  </div>
                </div>
                <input
                  type="file"
                  ref={fileInputRef}
                  accept=".pdf,.docx,.txt,.md,.json"
                  onChange={handleFileChange}
                  className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
                  title="Drop file here"
                />
              </div>

              {/* Actions */}
              <div className="flex items-center gap-6 pt-4">
                <button
                  onClick={handleCancel}
                  className="flex-1 py-4 px-8 bg-slate-50 hover:bg-slate-100 text-slate-700 font-headline text-base font-semibold transition-all rounded-full border border-slate-200 flex items-center justify-center gap-2 cursor-pointer"
                  type="button"
                >
                  Clear
                </button>
                <button
                  onClick={handleUpload}
                  disabled={status === "uploading" || !selectedFile}
                  className={`flex-[2] py-4 px-8 rounded-full font-headline text-base font-semibold transition-all active:scale-95 shadow-md flex items-center justify-center gap-2 cursor-pointer ${
                    status === "uploading" || !selectedFile
                      ? "bg-slate-300 text-slate-505 cursor-not-allowed shadow-none"
                      : "bg-blue-600 hover:bg-blue-700 text-white shadow-blue-200 hover:shadow-lg hover:-translate-y-0.5"
                  }`}
                  type="button"
                >
                  Upload Asset
                </button>
              </div>
            </form>
          </div>
        </div>

        {/* Real-time Ingestion Progress Section */}
        {processingDocs.length > 0 && (
          <div className="bg-white rounded-[2rem] border border-slate-100 p-8 shadow-[0_15px_40px_rgba(0,0,0,0.02)] space-y-6">
            <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2.5 pb-2 border-b border-slate-100">
              <span className="material-symbols-outlined text-base animate-spin text-blue-600">sync</span>
              Active Ingestion Queue
            </h3>
            
            <div className="space-y-6">
              {processingDocs.map((doc) => (
                <div key={doc.id} className="bg-slate-50 border border-slate-100 rounded-2xl p-6 space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="material-symbols-outlined text-xl text-blue-500">description</span>
                      <span className="text-sm font-bold text-slate-800 truncate max-w-sm" title={doc.filename}>
                        {doc.filename}
                      </span>
                    </div>
                    
                    <span className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider border ${
                      doc.status === 'completed' ? 'bg-emerald-50 text-emerald-700 border-emerald-100' :
                      doc.status === 'failed' ? 'bg-red-50 text-red-700 border-red-100' :
                      'bg-blue-50 text-blue-700 border-blue-100'
                    }`}>
                      {STEP_LABELS[doc.step] || doc.step}
                    </span>
                  </div>

                  {doc.status === 'processing' && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-xs text-slate-400 font-bold">
                        <span>{doc.detail || "Waiting to start…"}</span>
                        <span>{doc.pct}% · ETA {STEP_ETA[doc.step] || '…'}</span>
                      </div>
                      <div className="h-3 w-full bg-slate-200 rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-blue-600 rounded-full transition-all duration-500" 
                          style={{ width: `${Math.max(doc.pct, 5)}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {doc.status === 'completed' && (
                    <div className="flex items-center gap-2 text-sm text-emerald-600 font-semibold">
                      <CheckCircle className="h-5 w-5" />
                      <span>Ingestion completed! Added to vector index.</span>
                    </div>
                  )}

                  {doc.status === 'failed' && (
                    <div className="space-y-1.5">
                      <div className="flex items-center gap-2 text-sm text-red-600 font-semibold">
                        <AlertCircle className="h-5 w-5" />
                        <span>Extraction failed</span>
                      </div>
                      <p className="text-xs text-red-500/80 leading-normal pl-7">
                        {doc.error_message || "Unknown parser error."}
                      </p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  );
};

export default UploadFile;
