import { useState, useRef, useEffect } from "react";
import { Search, ChevronDown, Tag, X } from "lucide-react";
import { apiFetch, endpoints } from "../lib/api";

const Filter = ({ onSearch, onClear, onFilterChange }) => {
  const [query, setQuery] = useState("");
  const [selectedTag, setSelectedTag] = useState("");
  const [docType, setDocType] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  
  // Dropdown states
  const [isTypeOpen, setIsTypeOpen] = useState(false);
  const [isTagOpen, setIsTagOpen] = useState(false);
  const [tagList, setTagList] = useState([]);
  
  const typeRef = useRef(null);
  const tagRef = useRef(null);

  const documentTypes = [
    { label: "All Types", value: "" },
    { label: "Syllabi", value: "syllabus" },
    { label: "Lecture Notes", value: "notes" },
    { label: "Assignments", value: "assign" },
    { label: "Other Documents", value: "other" }
  ];

  useEffect(() => {
    // Fetch tags to populate tag suggestion dropdown
    apiFetch(endpoints.documents.tags)
      .then(data => {
        if (data && data.flat) {
          setTagList(data.flat.map(t => t.name));
        }
      })
      .catch(err => console.error("Error loading tags:", err));
  }, []);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (typeRef.current && !typeRef.current.contains(event.target)) {
        setIsTypeOpen(false);
      }
      if (tagRef.current && !tagRef.current.contains(event.target)) {
        setIsTagOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSearchSubmit = () => {
    onSearch(query);
  };

  const handleFilterUpdate = (key, value) => {
    let updatedFilters = {
      query,
      tag: selectedTag,
      docType,
      fromDate,
      toDate,
      [key]: value
    };

    if (key === "tag") setSelectedTag(value);
    if (key === "docType") setDocType(value);
    if (key === "fromDate") setFromDate(value);
    if (key === "toDate") setToDate(value);

    onFilterChange(updatedFilters);
  };

  const handleClear = () => {
    setQuery("");
    setSelectedTag("");
    setDocType("");
    setFromDate("");
    setToDate("");
    onClear();
  };

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm mb-8 animate-in fade-in slide-in-from-top-3 duration-300">
      <div className="flex flex-wrap items-end gap-6">
        {/* Search Input / Query */}
        <div className="flex-1 min-w-[200px] flex flex-col">
          <label className="text-xs font-headline font-bold text-slate-500 uppercase tracking-wider mb-2 ml-1">
            Search Content / FileName
          </label>
          <div className="relative">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 h-5 w-5" />
            <input
              type="text"
              placeholder="Search content or filenames..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearchSubmit()}
              className="h-12 w-full pl-11 pr-4 rounded-xl border border-slate-200 bg-slate-50 text-base focus:outline-none focus:ring-2 focus:ring-blue-500/10 focus:border-blue-500/50 transition-all font-body text-slate-800 placeholder-slate-400"
            />
          </div>
        </div>

        {/* Custom Tag Dropdown */}
        <div className="relative w-full md:w-56 flex flex-col" ref={tagRef}>
          <label className="text-xs font-headline font-bold text-slate-500 uppercase tracking-wider mb-2 ml-1">
            Filter by Tag
          </label>
          <div
            onClick={() => setIsTagOpen(!isTagOpen)}
            className="h-12 flex items-center justify-between px-4 rounded-xl border border-slate-200 bg-slate-50 cursor-pointer transition-all hover:border-slate-300"
          >
            <span className={`text-base truncate flex items-center gap-2 ${selectedTag ? "text-slate-800 font-semibold" : "text-slate-400"}`}>
              <Tag className="h-4 w-4 text-slate-400 shrink-0" />
              {selectedTag ? `#${selectedTag}` : "Select Tag"}
            </span>
            <ChevronDown className={`h-5 w-5 text-slate-400 transition-transform ${isTagOpen ? "rotate-180" : ""}`} />
          </div>

          {isTagOpen && (
            <div className="absolute top-[110%] left-0 w-full bg-white border border-slate-200 rounded-xl shadow-xl z-[60] py-1 max-h-56 overflow-y-auto animate-in fade-in slide-in-from-top-1 duration-200">
              <div
                onClick={() => {
                  handleFilterUpdate("tag", "");
                  setIsTagOpen(false);
                }}
                className={`px-4 py-2.5 text-base cursor-pointer transition-colors ${
                  selectedTag === ""
                    ? "bg-blue-50 text-blue-600 font-semibold"
                    : "hover:bg-slate-50 text-slate-600 hover:text-slate-800"
                }`}
              >
                All Tags
              </div>
              {tagList.map((tag) => (
                <div
                  key={tag}
                  onClick={() => {
                    handleFilterUpdate("tag", tag);
                    setIsTagOpen(false);
                  }}
                  className={`px-4 py-2.5 text-base cursor-pointer transition-colors flex items-center gap-2 ${
                    selectedTag === tag
                      ? "bg-blue-50 text-blue-600 font-semibold"
                      : "hover:bg-slate-50 text-slate-600 hover:text-slate-800"
                  }`}
                >
                  <Tag className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                  #{tag}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Date Filters */}
        <div className="flex items-end gap-3">
          <div className="flex flex-col">
            <label className="text-xs font-headline font-bold text-slate-500 uppercase tracking-wider mb-2 ml-1">
              From
            </label>
            <input
              type="date"
              value={fromDate}
              max={new Date().toISOString().split("T")[0]}
              onChange={(e) => handleFilterUpdate("fromDate", e.target.value)}
              className="h-12 px-4 rounded-xl border border-slate-200 bg-slate-50 text-base focus:outline-none focus:ring-2 focus:ring-blue-500/10 focus:border-blue-500/50 transition-all font-body text-slate-700"
            />
          </div>
          <div className="flex flex-col">
            <label className="text-xs font-headline font-bold text-slate-500 uppercase tracking-wider mb-2 ml-1">
              To
            </label>
            <input
              type="date"
              value={toDate}
              max={new Date().toISOString().split("T")[0]}
              onChange={(e) => handleFilterUpdate("toDate", e.target.value)}
              className="h-12 px-4 rounded-xl border border-slate-200 bg-slate-50 text-base focus:outline-none focus:ring-2 focus:ring-blue-500/10 focus:border-blue-500/50 transition-all font-body text-slate-700"
            />
          </div>
        </div>

        {/* Document Type Dropdown */}
        <div className="relative w-full md:w-60" ref={typeRef}>
          <label className="text-xs font-headline font-bold text-slate-500 uppercase tracking-wider mb-2 ml-1">
            Document Type
          </label>
          <div
            onClick={() => setIsTypeOpen(!isTypeOpen)}
            className="h-12 flex items-center justify-between px-4 rounded-xl border border-slate-200 bg-slate-50 cursor-pointer transition-all hover:border-slate-300"
          >
            <span className={`text-base truncate ${docType ? "text-slate-800 font-semibold" : "text-slate-400"}`}>
              {documentTypes.find(t => t.value === docType)?.label || "Select Type"}
            </span>
            <ChevronDown className={`h-5 w-5 text-slate-400 transition-transform ${isTypeOpen ? "rotate-180" : ""}`} />
          </div>

          {isTypeOpen && (
            <div className="absolute top-[110%] left-0 w-full bg-white border border-slate-200 rounded-xl shadow-xl z-[60] py-1 animate-in fade-in slide-in-from-top-1 duration-200">
              {documentTypes.map((type) => (
                <div
                  key={type.value}
                  onClick={() => {
                    handleFilterUpdate("docType", type.value);
                    setIsTypeOpen(false);
                  }}
                  className={`px-4 py-2.5 text-base cursor-pointer transition-colors ${
                    docType === type.value
                      ? "bg-blue-50 text-blue-600 font-semibold"
                      : "hover:bg-slate-50 text-slate-600 hover:text-slate-800"
                  }`}
                >
                  {type.label}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Search & Clear Buttons */}
        <div className="flex items-center gap-3">
          <button
            onClick={handleSearchSubmit}
            className="h-12 px-8 bg-blue-600 text-white rounded-xl text-base font-headline font-semibold hover:bg-blue-700 shadow-md hover:shadow-lg transition-all cursor-pointer"
          >
            Search
          </button>
          <button
            onClick={handleClear}
            className="h-12 px-6 bg-white text-slate-600 rounded-xl text-base font-headline border border-slate-200 hover:bg-slate-50 transition-all cursor-pointer font-medium"
          >
            Clear
          </button>
        </div>
      </div>
    </div>
  );
};

export default Filter;
