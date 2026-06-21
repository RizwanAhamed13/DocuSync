import { useState, useEffect } from "react";
import { NavLink } from "react-router-dom";
import { apiFetch, endpoints } from "../lib/api";
import {
  Home,
  Upload,
  Menu,
  ChevronLeft,
  Server,
  Database,
  Cpu
} from "lucide-react";

const SidePanel = () => {
  const [isExpanded, setIsExpanded] = useState(true);
  const [healthData, setHealthData] = useState(null);

  const navItems = [
    { id: "home", label: "Library", icon: Home },
    { id: "upload", label: "Upload Asset", icon: Upload },
  ];

  const fetchHealth = () => {
    apiFetch(endpoints.documents.health)
      .then(data => setHealthData(data))
      .catch(err => console.error("Health check failed:", err));
  };

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <aside
      className={`flex flex-col h-screen bg-white border-r border-slate-200 transition-all duration-300 ease-in-out font-body z-45 shrink-0 ${
        isExpanded ? "w-64" : "w-20"
      }`}
    >
      {/* Header Section */}
      <div className="flex items-center justify-between px-4 py-6 border-b border-slate-100">
        {isExpanded ? (
          <>
            <div className="flex flex-col animate-in fade-in slide-in-from-left-2 duration-300">
              <span className="text-blue-600 font-headline font-bold text-lg tracking-tight flex items-center gap-1.5">
                <span className="material-symbols-outlined !text-2xl">sync</span>
                DocuSync
              </span>
              <span className="text-[9px] text-slate-400 font-medium uppercase tracking-widest pl-1 mt-0.5">
                Local Intelligence
              </span>
            </div>
            <button
              onClick={() => setIsExpanded((prev) => !prev)}
              className="p-2 rounded-xl hover:bg-blue-50 text-slate-400 hover:text-blue-600 transition-all duration-200 shadow-sm border border-transparent hover:border-blue-100 cursor-pointer"
              aria-label="Toggle sidebar"
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
          </>
        ) : (
          <button
            onClick={() => setIsExpanded((prev) => !prev)}
            className="p-2.5 mx-auto rounded-xl hover:bg-blue-50 text-slate-400 hover:text-blue-600 transition-all duration-200 shadow-sm border border-slate-200 hover:border-blue-200 cursor-pointer"
            aria-label="Toggle sidebar"
          >
            <Menu className="h-5 w-5" />
          </button>
        )}
      </div>

      {/* Navigation Links */}
      <nav className="flex flex-col gap-2 px-3 py-6 flex-1 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.id}
              to={`/${item.id}`}
              title={!isExpanded ? item.label : ""}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-3 rounded-xl transition-all duration-200 group relative ${
                  isActive
                    ? "bg-blue-600 text-white shadow-md shadow-blue-200 font-medium"
                    : "text-slate-500 hover:bg-blue-50 hover:text-blue-600"
                }`
              }
            >
              <Icon
                className={`flex-shrink-0 transition-transform duration-300 group-hover:scale-110 ${
                  isExpanded ? "h-5 w-5" : "h-6 w-6 mx-auto"
                }`}
              />
              {isExpanded && (
                <span className="text-sm font-headline whitespace-nowrap animate-in fade-in slide-in-from-left-2 duration-300">
                  {item.label}
                </span>
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* Footer Section - System Status Widget */}
      <div className="mt-auto px-3 py-6 border-t border-slate-100 space-y-2">
        {isExpanded ? (
          <div className="p-3.5 rounded-2xl bg-slate-50 border border-slate-100 animate-in fade-in slide-in-from-bottom-2 duration-400 space-y-3">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-700">
              <Server className="h-4 w-4 text-blue-600" />
              <span>Local Server</span>
              <span className="ml-auto flex h-2 w-2 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
            </div>
            
            <div className="space-y-1.5 text-[11px] text-slate-500">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1"><Database className="h-3 w-3" /> Vectors:</span>
                <span className="font-semibold text-slate-800">
                  {healthData?.vector_store?.chunks ?? 0} chunks
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1"><Cpu className="h-3 w-3" /> Model:</span>
                <span className="font-semibold text-slate-800 truncate max-w-[100px]" title={healthData?.embedding_model}>
                  {healthData?.embedding_model ? healthData.embedding_model.split('/').pop() : "None"}
                </span>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center">
            <div className="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center border border-blue-100 shadow-sm relative" title="Server Status: Active">
              <Server className="h-5 w-5" />
              <span className="absolute top-0 right-0 block h-2.5 w-2.5 rounded-full ring-2 ring-white bg-emerald-400"></span>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
};

export default SidePanel;
