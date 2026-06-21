import React, { useState, useEffect } from 'react';
import { Trash2, MoreVertical, Eye, Download, SearchX, X, Tag, FileText, CheckCircle, AlertCircle, RefreshCw } from 'lucide-react';
import { apiFetch, endpoints } from '../lib/api';
import Filter from './Filter';

const View = () => {
  const [data, setData] = useState([]);
  const [searchResults, setSearchResults] = useState(null); // null means showing standard library list
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedIds, setSelectedIds] = useState([]);
  const [openActionMenuId, setOpenActionMenuId] = useState(null);
  const [activeActionFile, setActiveActionFile] = useState(null);
  
  // Status & Notification
  const [status, setStatus] = useState("idle"); // idle, loading, success, error
  const [message, setMessage] = useState("");

  // Stats Counters
  const [stats, setStats] = useState({ all: 0, processing: 0, failed: 0 });

  // Inspector Popup Modal state
  const [inspectorDoc, setInspectorDoc] = useState(null);
  const [inspectorText, setInspectorText] = useState("");
  const [loadingText, setLoadingText] = useState(false);

  // Client-side Filters
  const [filters, setFilters] = useState({
    query: "",
    tag: "",
    docType: "",
    fromDate: "",
    toDate: "",
  });

  const fetchTableData = (showToast = true) => {
    if (showToast) {
      setStatus("loading");
      setMessage("Refreshing document database...");
    }
    
    apiFetch(endpoints.documents.all)
      .then(json => {
        setData(json || []);
        updateStats(json || []);
        if (showToast) {
          setStatus("success");
          setMessage("Refreshed successfully!");
          setTimeout(() => setStatus("idle"), 2500);
        }
      })
      .catch(error => {
        console.error("Error fetching data:", error);
        if (showToast) {
          setStatus("error");
          setMessage(error.message || "Failed to fetch document list.");
          setTimeout(() => setStatus("idle"), 3000);
        }
      });
  };

  const updateStats = (docs) => {
    const all = docs.filter(d => d.status === "completed").length;
    const processing = docs.filter(d => d.status === "processing").length;
    const failed = docs.filter(d => d.status === "failed").length;
    setStats({ all, processing, failed });
  };

  // Poll database if any documents are in 'processing' status
  useEffect(() => {
    fetchTableData(false);
    
    const interval = setInterval(() => {
      // Check if there are processing documents
      const hasProcessing = data.some(d => d.status === 'processing');
      if (hasProcessing || data.length === 0) {
        fetchTableData(false);
      }
    }, 4000);

    return () => clearInterval(interval);
  }, [data]);

  // Handle clicking outside action menu to close it
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (!event.target.closest('.action-menu-container')) {
        setOpenActionMenuId(null);
      }
    };
    if (openActionMenuId) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [openActionMenuId]);

  // Execute hybrid semantic search
  const handleSearch = (queryText) => {
    if (!queryText.trim()) {
      setSearchResults(null);
      setSearchQuery("");
      return;
    }

    setStatus("loading");
    setMessage("Running semantic AI search...");
    setSearchQuery(queryText);

    apiFetch(endpoints.documents.search, {
      method: "POST",
      body: JSON.stringify({ query: queryText, limit: 8 })
    })
      .then(hits => {
        setSearchResults(hits || []);
        setStatus("success");
        setMessage(`Found ${hits.length} semantic matches.`);
        setTimeout(() => setStatus("idle"), 2500);
      })
      .catch(err => {
        console.error("Search failed:", err);
        setStatus("error");
        setMessage(err.message || "Search failed.");
        setTimeout(() => setStatus("idle"), 3000);
      });
  };

  const handleClearSearch = () => {
    setSearchResults(null);
    setSearchQuery("");
    fetchTableData(false);
  };

  const handleFilterChange = (newFilters) => {
    setFilters(newFilters);
  };

  // Delete document
  const handleDeleteDoc = (docId, filename) => {
    if (!confirm(`Are you sure you want to delete "${filename}"?`)) return;

    setStatus("loading");
    setMessage("Deleting asset...");
    setOpenActionMenuId(null);

    apiFetch(endpoints.documents.delete(docId), {
      method: 'DELETE'
    })
      .then(() => {
        setData(prev => prev.filter(item => item.id !== docId));
        setSelectedIds(prev => prev.filter(id => id !== docId));
        if (inspectorDoc && inspectorDoc.id === docId) {
          setInspectorDoc(null);
        }
        setStatus("success");
        setMessage("Document deleted successfully!");
        setTimeout(() => setStatus("idle"), 2500);
        fetchTableData(false);
      })
      .catch(err => {
        console.error("Delete failed:", err);
        setStatus("error");
        setMessage(err.message || "Failed to delete document.");
        setTimeout(() => setStatus("idle"), 3000);
      });
  };

  // Bulk Delete
  const handleBulkDelete = () => {
    if (!confirm(`Are you sure you want to delete the ${selectedIds.length} selected assets?`)) return;

    setStatus("loading");
    setMessage(`Deleting ${selectedIds.length} assets...`);

    // Sequentially delete selected docs since backend expects /documents/{id} DELETE
    const deletePromises = selectedIds.map(id => 
      apiFetch(endpoints.documents.delete(id), { method: 'DELETE' })
    );

    Promise.all(deletePromises)
      .then(() => {
        setSelectedIds([]);
        setStatus("success");
        setMessage("Selected documents deleted!");
        setTimeout(() => setStatus("idle"), 2500);
        fetchTableData(true);
      })
      .catch(err => {
        console.error("Bulk delete failed:", err);
        setStatus("error");
        setMessage("Failed to delete all selected items.");
        setTimeout(() => setStatus("idle"), 3000);
      });
  };

  // Open inspector popup and fetch full text
  const openInspector = (doc) => {
    setInspectorDoc(doc);
    setInspectorText("");
    setLoadingText(true);

    apiFetch(endpoints.documents.text(doc.id))
      .then(res => {
        setInspectorText(res.text || "No text available.");
        setLoadingText(false);
      })
      .catch(err => {
        console.error("Failed to load text:", err);
        setInspectorText("Error loading full text content.");
        setLoadingText(false);
      });
  };

  const closeInspector = () => {
    setInspectorDoc(null);
    setInspectorText("");
  };

  // Client-side filtering logic on the dataset
  const getFilteredData = () => {
    let result = [...data];

    // Filter by type
    if (filters.docType) {
      result = result.filter(d => d.doc_type === filters.docType);
    }

    // Filter by tag
    if (filters.tag) {
      result = result.filter(d => d.tags && d.tags.includes(filters.tag));
    }

    // Filter by date range
    if (filters.fromDate) {
      result = result.filter(d => new Date(d.upload_date) >= new Date(filters.fromDate));
    }
    if (filters.toDate) {
      result = result.filter(d => {
        const nextDay = new Date(filters.toDate);
        nextDay.setDate(nextDay.getDate() + 1);
        return new Date(d.upload_date) < nextDay;
      });
    }

    return result;
  };

  const filteredData = getFilteredData();
  const fileIcon = (filename) => {
    const lower = filename.toLowerCase();
    if (lower.endsWith('.pdf')) return 'fa-file-pdf text-red-500';
    if (lower.endsWith('.docx') || lower.endsWith('.doc')) return 'fa-file-word text-blue-500';
    return 'fa-file-lines text-slate-500';
  };

  return (
    <div className="h-full w-full text-on-surface bg-slate-50 font-body overflow-hidden flex flex-col relative">
      <div className="h-full w-full flex flex-col overflow-hidden">
        
        {/* Header Section */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-8 mt-1 shrink-0">
          <div>
            <h1 className="text-3xl font-headline font-bold text-on-surface flex items-center gap-3">
              <span className="material-symbols-outlined text-blue-600 !text-4xl">folder_shared</span>
              Digital Asset Library
            </h1>
            <p className="text-sm text-slate-500 mt-1">Explore, search, and audit your local files with local intelligence models.</p>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={() => fetchTableData(true)}
              disabled={status === "loading"}
              className="inline-flex items-center justify-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-xl shadow-md hover:shadow-lg transition-all disabled:opacity-50 text-sm font-headline font-semibold cursor-pointer"
            >
              <RefreshCw className={`h-4 w-4 ${status === "loading" ? "animate-spin" : ""}`} />
              Sync Database
            </button>
            {selectedIds.length > 0 && (
              <button
                onClick={handleBulkDelete}
                className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl text-sm font-headline font-semibold bg-red-50 text-red-600 border border-red-100 hover:bg-red-100 transition-all cursor-pointer"
              >
                <Trash2 className="h-4 w-4" />
                Delete Selected ({selectedIds.length})
              </button>
            )}
          </div>
        </div>

        {/* Global Toast Messages */}
        {status !== "idle" && (
          <div className={`mb-4 p-3.5 rounded-xl text-sm font-medium transition-all duration-300 animate-in fade-in zoom-in-95 shrink-0 ${
            status === "success" ? "bg-emerald-50 text-emerald-700 border border-emerald-100" :
            status === "error" ? "bg-red-50 text-red-700 border border-red-100" :
            "bg-blue-50 text-blue-700 border border-blue-100"
          }`}>
            <div className="flex items-center gap-2">
              {status === "success" && <CheckCircle className="h-4.5 w-4.5 text-emerald-500" />}
              {status === "error" && <AlertCircle className="h-4.5 w-4.5 text-red-500" />}
              {status === "loading" && <span className="material-symbols-outlined text-lg animate-spin text-blue-500">sync</span>}
              <span>{message}</span>
            </div>
          </div>
        )}

        {/* Stats Metrics Cards */}
        <div className="grid grid-cols-3 gap-6 mb-7 shrink-0">
          <div className="bg-white border border-slate-200/80 rounded-2xl p-6 md:p-8 shadow-sm flex items-center gap-6">
            <div className="p-4 bg-emerald-50 rounded-2xl text-emerald-600">
              <CheckCircle className="h-8 w-8" />
            </div>
            <div>
              <div className="text-3xl md:text-4xl font-headline font-bold text-slate-800">{stats.all}</div>
              <div className="text-xs text-slate-400 font-bold uppercase tracking-wider mt-0.5">Processed</div>
            </div>
          </div>
          <div className="bg-white border border-slate-200/80 rounded-2xl p-6 md:p-8 shadow-sm flex items-center gap-6">
            <div className="p-4 bg-blue-50 rounded-2xl text-blue-600">
              <span className="material-symbols-outlined !text-3xl animate-spin">sync</span>
            </div>
            <div>
              <div className="text-3xl md:text-4xl font-headline font-bold text-slate-800">{stats.processing}</div>
              <div className="text-xs text-slate-400 font-bold uppercase tracking-wider mt-0.5">Processing</div>
            </div>
          </div>
          <div className="bg-white border border-slate-200/80 rounded-2xl p-6 md:p-8 shadow-sm flex items-center gap-6">
            <div className="p-4 bg-red-50 rounded-2xl text-red-600">
              <AlertCircle className="h-8 w-8" />
            </div>
            <div>
              <div className="text-3xl md:text-4xl font-headline font-bold text-slate-800">{stats.failed}</div>
              <div className="text-xs text-slate-400 font-bold uppercase tracking-wider mt-0.5">Failed</div>
            </div>
          </div>
        </div>

        {/* Filters and Search Bar */}
        <div className="shrink-0">
          <Filter
            onSearch={handleSearch}
            onClear={handleClearSearch}
            onFilterChange={handleFilterChange}
          />
        </div>

        {/* Content Area - Semantic Hits OR Files Table */}
        <div className="bg-white border border-slate-200 rounded-2xl shadow-[0_10px_35px_rgba(0,0,0,0.03)] overflow-hidden flex-1 flex flex-col min-h-0 relative">
          
          {searchResults !== null ? (
            /* --- RENDER SEMANTIC SEARCH RESULTS --- */
            <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-2 shrink-0">
                <span className="text-xs font-bold text-slate-400 uppercase tracking-widest">
                  Matched Passages for "{searchQuery}"
                </span>
                <button
                  onClick={handleClearSearch}
                  className="text-xs text-blue-600 hover:text-blue-800 font-semibold cursor-pointer"
                >
                  Return to Library
                </button>
              </div>

              {searchResults.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {searchResults.map((hit) => (
                    <div
                      key={hit.chunk_id}
                      onClick={() => openInspector(data.find(d => d.id === hit.document_id) || { id: hit.document_id, filename: hit.filename, summary: hit.summary, tags: hit.tags })}
                      className="bg-slate-50 hover:bg-blue-50/30 border border-slate-200/60 hover:border-blue-200 rounded-2xl p-4 transition-all duration-200 cursor-pointer flex flex-col justify-between group"
                    >
                      <div>
                        <div className="flex items-center justify-between mb-2.5">
                          <span className="text-xs font-bold text-blue-600 bg-blue-100/50 px-2.5 py-0.5 rounded-full">
                            Similarity: {Math.round(hit.similarity * 100)}%
                          </span>
                          <span className="text-[10px] text-slate-400 font-medium">
                            Page {hit.page}
                          </span>
                        </div>
                        <p className="text-xs text-slate-600 line-clamp-4 italic font-body mb-3 leading-relaxed">
                          "...{hit.text}..."
                        </p>
                      </div>
                      <div className="border-t border-slate-100 pt-2.5 mt-auto flex items-center gap-2">
                        <span className={`material-symbols-outlined text-sm ${fileIcon(hit.filename)}`}></span>
                        <span className="text-xs font-semibold text-slate-700 truncate group-hover:text-blue-600 transition-colors">
                          {hit.filename}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="py-20 text-center flex flex-col items-center justify-center text-slate-400">
                  <SearchX className="h-12 w-12 mb-4 opacity-25" />
                  <p className="text-sm font-semibold text-slate-700">No matching text passages found</p>
                  <p className="text-xs mt-1 text-slate-400">Try rephrasing your search or checking spelling.</p>
                </div>
              )}
            </div>
          ) : (
            /* --- RENDER DOCUMENT LIBRARY TABLE --- */
            <div className="flex-1 overflow-auto">
              <table className="w-full border-separate border-spacing-0 text-base">
                <thead className="sticky top-0 bg-white z-20">
                  <tr className="bg-slate-50/50">
                    <th className="h-14 px-4 w-[60px] border-b border-slate-200/80 text-center">
                      <div className="relative flex items-center justify-center w-4 h-4 mx-auto">
                        <input
                          type="checkbox"
                          checked={filteredData.length > 0 && selectedIds.length === filteredData.length}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setSelectedIds(filteredData.map(d => d.id));
                            } else {
                              setSelectedIds([]);
                            }
                          }}
                          className="peer w-4 h-4 appearance-none rounded border border-slate-300 bg-white checked:bg-blue-600 checked:border-blue-600 cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-600/20 transition-colors duration-200"
                        />
                        <svg className="absolute w-3 h-3 text-white pointer-events-none opacity-0 peer-checked:opacity-100 transition-opacity duration-200" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                          <path fillRule="evenodd" clipRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"></path>
                        </svg>
                      </div>
                    </th>
                    <th className="h-14 px-4 text-left align-middle font-headline font-bold text-xs text-slate-500 uppercase tracking-wider border-b border-slate-200/80">
                      Date Uploaded
                    </th>
                    <th className="h-14 px-4 text-left align-middle font-headline font-bold text-xs text-slate-500 uppercase tracking-wider border-b border-slate-200/80">
                      Tags
                    </th>
                    <th className="h-14 px-4 text-left align-middle font-headline font-bold text-xs text-slate-500 uppercase tracking-wider border-b border-slate-200/80">
                      Pages & Size
                    </th>
                    <th className="h-14 px-4 text-left align-middle font-headline font-bold text-xs text-slate-500 uppercase tracking-wider border-b border-slate-200/80">
                      FileName
                    </th>
                    <th className="h-14 px-4 text-center align-middle font-headline font-bold text-xs text-slate-500 uppercase tracking-wider w-[100px] border-b border-slate-200/80">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="[&_tr:last-child_td]:border-b-0">
                  {filteredData.length > 0 ? (
                    filteredData.map((item, index) => {
                      const isLastRow = filteredData.length > 2 && index >= filteredData.length - 2;
                      const sizeKb = item.file_size_bytes ? (item.file_size_bytes / 1024).toFixed(1) : "0";
                      
                      return (
                        <tr key={item.id} className="transition-colors hover:bg-blue-50/20 group">
                          {/* Selection Checkbox */}
                          <td className="p-3 align-middle border-b border-slate-100 text-center">
                            <div className="relative flex items-center justify-center w-4 h-4 mx-auto">
                              <input
                                type="checkbox"
                                checked={selectedIds.includes(item.id)}
                                onChange={(e) => {
                                  if (e.target.checked) {
                                    setSelectedIds(prev => [...prev, item.id]);
                                  } else {
                                    setSelectedIds(prev => prev.filter(id => id !== item.id));
                                  }
                                }}
                                className="peer w-4 h-4 appearance-none rounded border border-slate-300 bg-white checked:bg-blue-600 checked:border-blue-600 cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-600/20 transition-colors duration-200"
                              />
                              <svg className="absolute w-3 h-3 text-white pointer-events-none opacity-0 peer-checked:opacity-100 transition-opacity duration-200" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                                <path fillRule="evenodd" clipRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"></path>
                              </svg>
                            </div>
                          </td>

                          {/* Upload Date */}
                          <td className="p-4 align-middle text-slate-500 text-sm whitespace-nowrap border-b border-slate-100">
                            {new Date(item.upload_date).toLocaleDateString("en-US", {
                              month: "short",
                              day: "2-digit",
                              year: "numeric",
                            })}
                          </td>

                          {/* Display Tags Pill List with Icon */}
                          <td className="p-4 align-middle border-b border-slate-100 max-w-[400px]">
                            {item.status === "processing" ? (
                              <span className="text-xs text-slate-400 italic">Extracting tags...</span>
                            ) : (
                              <div className="flex flex-wrap gap-1.5">
                                {item.tags && item.tags.length > 0 ? (
                                  item.tags.slice(0, 6).map(t => (
                                    <span key={t} className="inline-flex items-center gap-1 rounded-full bg-blue-50 border border-blue-100 px-2.5 py-0.5 text-xs font-semibold text-blue-700">
                                      <Tag className="h-3 w-3 text-blue-500 shrink-0" />
                                      {t}
                                    </span>
                                  ))
                                ) : (
                                  <span className="text-xs text-slate-400 italic">No tags</span>
                                )}
                                {item.tags && item.tags.length > 6 && (
                                  <span className="text-[10px] text-slate-400 font-bold self-center ml-0.5" title={item.tags.slice(6).join(', ')}>
                                    +{item.tags.length - 6}
                                  </span>
                                )}
                              </div>
                            )}
                          </td>

                          {/* Size & Page Count */}
                          <td className="p-4 align-middle text-slate-500 text-sm border-b border-slate-100">
                            {item.status === "processing" ? (
                              <span className="text-blue-500 font-medium italic animate-pulse">Analyzing...</span>
                            ) : (
                              `${item.page_count} pgs · ${sizeKb} KB`
                            )}
                          </td>

                          {/* File Name */}
                          <td className="p-4 align-middle font-headline font-bold text-base text-slate-800 border-b border-slate-100">
                            <div className="flex items-center gap-3">
                              <span className={`material-symbols-outlined text-xl ${fileIcon(item.filename)}`}></span>
                              <span className="truncate max-w-xs md:max-w-lg lg:max-w-xl xl:max-w-4xl block" title={item.filename}>{item.filename}</span>
                            </div>
                          </td>

                          {/* Action Button Dropdown */}
                          <td className="p-4 align-middle text-center border-b border-slate-100">
                             <div className="relative inline-block text-left action-menu-container">
                               <button
                                 onClick={() => setOpenActionMenuId(openActionMenuId === item.id ? null : item.id)}
                                 className="flex h-9 w-9 mx-auto items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 shadow-sm hover:bg-slate-50 hover:text-blue-600 transition-all cursor-pointer focus:outline-none shrink-0"
                               >
                                 <MoreVertical className="h-4 w-4" />
                               </button>

                               {openActionMenuId === item.id && (
                                 <div className={`absolute right-0 w-40 bg-white rounded-xl shadow-[0_10px_40px_rgba(0,0,0,0.12)] border border-slate-200 py-2 z-[100] font-body duration-200 ${
                                   isLastRow 
                                     ? 'bottom-full mb-1 animate-in fade-in slide-in-from-bottom-2' 
                                     : 'top-full mt-1 animate-in fade-in slide-in-from-top-2'
                                 }`}>
                                   <button
                                     onClick={() => {
                                       setOpenActionMenuId(null);
                                       openInspector(item);
                                     }}
                                     disabled={item.status !== "completed"}
                                     className="w-full text-left px-4 py-2.5 text-sm text-slate-600 hover:bg-slate-50 hover:text-blue-600 flex items-center gap-2 transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer font-medium"
                                   >
                                     <Eye className="h-4 w-4" /> View Insights
                                   </button>

                                   <a
                                     href={`/documents/${item.id}/download`}
                                     target="_blank"
                                     rel="noreferrer"
                                     onClick={() => setOpenActionMenuId(null)}
                                     className="w-full text-left px-4 py-2.5 text-sm text-slate-600 hover:bg-slate-50 hover:text-blue-600 flex items-center gap-2 transition-colors disabled:opacity-40 cursor-pointer no-underline block font-medium"
                                   >
                                     <Download className="h-4 w-4" /> Download
                                   </a>

                                   <button
                                     onClick={() => handleDeleteDoc(item.id, item.filename)}
                                     className="w-full text-left px-4 py-2.5 text-sm text-red-600 hover:bg-red-50 hover:text-red-700 flex items-center gap-2 transition-colors border-t border-slate-100 cursor-pointer font-medium"
                                   >
                                     <Trash2 className="h-4 w-4" /> Delete
                                   </button>
                                 </div>
                               )}
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan={6} className="py-20 text-center">
                        <div className="flex flex-col items-center justify-center text-slate-400">
                          <SearchX className="h-12 w-12 mb-4 opacity-25" />
                          <p className="text-sm font-semibold text-slate-700">No documents found</p>
                          <p className="text-xs mt-1 text-slate-400">Try uploading a document or clearing filters.</p>
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* --- AI INSIGHTS CENTERED POP-UP MODAL --- */}
      {inspectorDoc && (
        <div className="fixed inset-0 z-[150] flex items-center justify-center p-4">
          {/* Backdrop Blur Overlay */}
          <div
            className="absolute inset-0 bg-black/40 backdrop-blur-sm transition-opacity duration-300"
            onClick={closeInspector}
          />
          
          {/* Centered Modal Card */}
          <div className="relative w-full max-w-5xl bg-white rounded-3xl shadow-[0_25px_60px_rgba(0,0,0,0.15)] max-h-[85vh] flex flex-col z-[160] overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-8 py-5.5 border-b border-slate-200 shrink-0 bg-slate-50/50">
              <div className="flex items-center gap-3 min-w-0">
                <FileText className="h-6 w-6 text-blue-600 flex-shrink-0" />
                <h3 className="text-lg font-headline font-bold text-slate-800 truncate" title={inspectorDoc.filename}>
                  {inspectorDoc.filename}
                </h3>
              </div>
              <button
                onClick={closeInspector}
                className="h-9 w-9 inline-flex items-center justify-center rounded-xl hover:bg-slate-200/60 text-slate-400 hover:text-slate-700 transition-colors cursor-pointer"
              >
                <X className="h-6 w-6" />
              </button>
            </div>

            {/* Modal Scrollable Body */}
            <div className="flex-1 overflow-y-auto p-8 space-y-8">
              
              {/* Summary Section */}
              <div className="space-y-2.5">
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-1.5 font-headline">
                  <span className="material-symbols-outlined text-sm !text-slate-400">wysiwyg</span>
                  AI Summary
                </h4>
                <div className="bg-slate-50 border border-slate-100 rounded-2xl p-5 text-base text-slate-700 leading-relaxed font-body">
                  {inspectorDoc.summary || "No summary available."}
                </div>
              </div>

              {/* Tags Section */}
              <div className="space-y-2.5">
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-1.5 font-headline">
                  <Tag className="h-4 w-4 text-slate-400" />
                  Classified Tags
                </h4>
                <div className="flex flex-wrap gap-2 pt-0.5">
                  {inspectorDoc.tags && inspectorDoc.tags.length > 0 ? (
                    inspectorDoc.tags.map(t => (
                      <span key={t} className="inline-flex items-center gap-1.5 px-4 py-1.5 bg-blue-50 text-blue-700 border border-blue-100 text-sm font-semibold rounded-full">
                        <Tag className="h-3.5 w-3.5 text-blue-500 shrink-0" />
                        #{t}
                      </span>
                    ))
                  ) : (
                    <span className="text-sm text-slate-400 italic">No tags assigned.</span>
                  )}
                </div>
              </div>

              {/* Key Findings Section */}
              <div className="space-y-2.5">
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-1.5 font-headline">
                  <span className="material-symbols-outlined text-sm !text-slate-400">checklist</span>
                  Key Findings & Clauses
                </h4>
                <ul className="space-y-3.5 list-none p-0 m-0">
                  {inspectorDoc.key_findings && inspectorDoc.key_findings.length > 0 ? (
                    inspectorDoc.key_findings.map((f, i) => (
                      <li key={i} className="flex items-start gap-3 text-base text-slate-700 font-body leading-relaxed">
                        <CheckCircle className="h-5 w-5 text-blue-500 mt-0.5 shrink-0" />
                        <span>{f}</span>
                      </li>
                    ))
                  ) : (
                    <li className="text-sm text-slate-400 italic">No key findings extracted.</li>
                  )}
                </ul>
              </div>

              {/* Entities Section */}
              {inspectorDoc.entities && Object.keys(inspectorDoc.entities).length > 0 && (
                <div className="space-y-2.5">
                  <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-1.5 font-headline">
                    <span className="material-symbols-outlined text-sm !text-slate-400">fingerprint</span>
                    Extracted Entities
                  </h4>
                  <div className="bg-slate-50 border border-slate-100 rounded-2xl p-5 space-y-4">
                    {Object.entries(inspectorDoc.entities).map(([category, items]) => {
                      if (!items || items.length === 0) return null;
                      return (
                        <div key={category} className="space-y-1.5">
                          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block font-headline">{category}</span>
                          <div className="flex flex-wrap gap-2">
                            {items.map((item, idx) => (
                              <span key={idx} className="inline-block bg-white border border-slate-200/80 px-2.5 py-1 text-sm text-slate-600 rounded font-body">
                                {item}
                              </span>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Full Text Section */}
              <div className="space-y-2.5">
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-1.5 font-headline">
                  <FileText className="h-4 w-4 text-slate-400" />
                  Full Extracted Text
                </h4>
                <div className="border border-slate-200 rounded-2xl bg-slate-900/5 p-5 h-80 overflow-y-auto text-sm text-slate-700 font-mono whitespace-pre-wrap leading-relaxed">
                  {loadingText ? (
                    <div className="flex flex-col items-center justify-center h-full text-slate-400 space-y-2">
                      <span className="material-symbols-outlined animate-spin !text-2xl text-blue-600">sync</span>
                      <span>Streaming text blocks...</span>
                    </div>
                  ) : (
                    inspectorText
                  )}
                </div>
              </div>

            </div>

            {/* Modal Footer Actions */}
            <div className="px-6 py-4 border-t border-slate-200 bg-slate-50/50 flex items-center gap-3 shrink-0">
              <a
                href={`/documents/${inspectorDoc.id}/download`}
                target="_blank"
                rel="noreferrer"
                className="flex-1 inline-flex items-center justify-center gap-2 h-10 rounded-xl bg-blue-600 text-white font-headline text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm hover:shadow no-underline"
              >
                <Download className="h-4 w-4" /> Download Original
              </a>
              <button
                onClick={closeInspector}
                className="flex-1 h-10 rounded-xl border border-slate-200 bg-white text-sm font-headline font-medium text-slate-700 hover:bg-slate-100 transition-all cursor-pointer"
              >
                Close Insights
              </button>
            </div>

          </div>
        </div>
      )}

    </div>
  );
};

export default View;
