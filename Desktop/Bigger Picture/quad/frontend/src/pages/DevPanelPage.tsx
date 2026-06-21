import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useParams, useLocation } from 'react-router-dom';
import Editor from '@monaco-editor/react';
import { Terminal as XTerm } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import api from '../lib/api';
import {
  FileText,
  Save,
  Sparkles,
  TerminalSquare,
  Link2,
  Copy,
  ExternalLink,
  Send,
  BookOpen,
} from 'lucide-react';

interface FileEntry {
  path: string;
  type: string;
}

interface ChatMessage {
  role: 'user' | 'ai';
  text: string;
}

interface Tunnel {
  tunnel_id: string;
  app_name: string;
  subdomain: string;
  status: string;
  local_port: number;
}

interface Devlog {
  log_id: string;
  title: string;
  content: string;
  created_at: string;
}

type TabKey = 'ai' | 'terminal' | 'tunnel' | 'devlog';

function langFromPath(path: string): string {
  if (path.endsWith('.py')) return 'python';
  if (path.endsWith('.ts') || path.endsWith('.tsx')) return 'typescript';
  if (path.endsWith('.js') || path.endsWith('.jsx')) return 'javascript';
  if (path.endsWith('.json')) return 'json';
  if (path.endsWith('.html')) return 'html';
  if (path.endsWith('.css')) return 'css';
  if (path.endsWith('.md')) return 'markdown';
  return 'plaintext';
}

export const DevPanelPage: React.FC = () => {
  const { appName = '' } = useParams<{ appName: string }>();
  const location = useLocation();
  const queryParams = new URLSearchParams(location.search);
  const queryFile = queryParams.get('file');
  const queryLine = queryParams.get('line');

  const [files, setFiles] = useState<FileEntry[]>([]);
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [tab, setTab] = useState<TabKey>('ai');

  const editorRef = useRef<any>(null);

  const handleEditorDidMount = (editor: any, monaco: any) => {
    editorRef.current = editor;
  };

  useEffect(() => {
    if (files.length > 0 && queryFile) {
      const fileExists = files.some((f) => f.path === queryFile);
      if (fileExists && activeFile !== queryFile) {
        openFile(queryFile);
      }
    }
  }, [files, queryFile, activeFile]);

  useEffect(() => {
    if (editorRef.current && queryLine && activeFile === queryFile) {
      const lineNum = parseInt(queryLine, 10);
      if (!isNaN(lineNum)) {
        setTimeout(() => {
          if (editorRef.current) {
            editorRef.current.revealLineInCenter(lineNum);
            editorRef.current.setPosition({ lineNumber: lineNum, column: 1 });
            editorRef.current.focus();
          }
        }, 150);
      }
    }
  }, [activeFile, fileContent, queryLine, queryFile]);

  // AI chat state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [aiLoading, setAiLoading] = useState(false);

  // Tunnel state
  const [tunnels, setTunnels] = useState<Tunnel[]>([]);

  // Devlog state
  const [devlogs, setDevlogs] = useState<Devlog[]>([]);
  const [showLogEditor, setShowLogEditor] = useState(false);
  const [logTitle, setLogTitle] = useState('');
  const [logContent, setLogContent] = useState('');
  const [logBusy, setLogBusy] = useState(false);

  // Terminal
  const termContainerRef = useRef<HTMLDivElement | null>(null);
  const termRef = useRef<XTerm | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const loadFiles = useCallback(async () => {
    try {
      const resp = await api.get<{ files: FileEntry[] }>(`/deploy/files/${appName}`);
      setFiles(resp.data.files);
    } catch {
      setFiles([]);
    }
  }, [appName]);

  const loadTunnels = useCallback(async () => {
    try {
      const resp = await api.get<Tunnel[]>('/tunnels/');
      setTunnels(resp.data.filter((t) => t.app_name === appName));
    } catch {
      setTunnels([]);
    }
  }, [appName]);

  const loadDevlogs = useCallback(async () => {
    try {
      const resp = await api.get<Devlog[]>(`/devlog/${appName}`);
      setDevlogs(resp.data);
    } catch {
      setDevlogs([]);
    }
  }, [appName]);

  useEffect(() => {
    loadFiles();
    loadTunnels();
    loadDevlogs();
  }, [loadFiles, loadTunnels, loadDevlogs]);

  const openFile = async (path: string) => {
    try {
      const resp = await api.get<{ content: string }>(
        `/deploy/file/${appName}?path=${encodeURIComponent(path)}`
      );
      setActiveFile(path);
      setFileContent(resp.data.content);
    } catch {
      setActiveFile(path);
      setFileContent('// Could not load file');
    }
  };

  const saveFile = async () => {
    if (!activeFile) return;
    setSaving(true);
    setSaveStatus('idle');
    try {
      await api.post(`/deploy/file/${appName}`, { path: activeFile, content: fileContent });
      setSaveStatus('success');
      setTimeout(() => setSaveStatus('idle'), 2000);
    } catch {
      setSaveStatus('error');
      setTimeout(() => setSaveStatus('idle'), 3000);
    } finally {
      setSaving(false);
    }
  };

  const sendChat = async () => {
    const text = chatInput.trim();
    if (!text || aiLoading) return;
    const history = messages.map((m) => ({
      role: m.role === 'ai' ? 'assistant' : 'user',
      content: m.text,
    }));
    setMessages((m) => [...m, { role: 'user', text }]);
    setChatInput('');
    setAiLoading(true);
    try {
      const resp = await api.post<{ reply: string }>('/ai/chat', {
        message: text,
        context_file: fileContent || undefined,
        app_name: appName,
        history,
      });
      setMessages((m) => [...m, { role: 'ai', text: resp.data.reply }]);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      setMessages((m) => [
        ...m,
        { role: 'ai', text: e.response?.data?.detail || 'Error contacting AI service.' },
      ]);
    } finally {
      setAiLoading(false);
    }
  };

  const createDevlog = async () => {
    if (!logTitle.trim() || !logContent.trim()) return;
    setLogBusy(true);
    try {
      await api.post(`/devlog/${appName}`, { title: logTitle, content: logContent });
      setLogTitle('');
      setLogContent('');
      setShowLogEditor(false);
      loadDevlogs();
    } catch {
      /* ignore */
    } finally {
      setLogBusy(false);
    }
  };

  // Terminal lifecycle - only when terminal tab is active
  useEffect(() => {
    if (tab !== 'terminal' || !termContainerRef.current) return;

    const term = new XTerm({
      fontSize: 13,
      theme: { background: '#ffffff', foreground: '#1a1a1a', cursor: '#3b5bdb' },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(termContainerRef.current);
    try {
      fit.fit();
    } catch {
      /* ignore */
    }
    termRef.current = term;

    const apiBase = (import.meta.env.VITE_API_URL as string) || 'http://localhost:8000';
    const wsBase = apiBase.replace(/^http/, 'ws');
    const ws = new WebSocket(`${wsBase}/terminal/ws/${appName}`);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onmessage = (ev: MessageEvent) => {
      if (ev.data instanceof ArrayBuffer) {
        term.write(new Uint8Array(ev.data));
      } else {
        term.write(ev.data as string);
      }
    };
    ws.onopen = () => term.write('Connected to terminal.\r\n');
    ws.onclose = () => term.write('\r\nConnection closed.\r\n');

    const disposable = term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(data);
    });

    return () => {
      disposable.dispose();
      ws.close();
      term.dispose();
      termRef.current = null;
      wsRef.current = null;
    };
  }, [tab, appName]);

  return (
    <div className="flex flex-col md:flex-row h-[calc(100vh-84px)] bg-white border border-slate-200 rounded-3xl overflow-hidden shadow-sm">
      {/* File tree - 140px, hidden on mobile */}
      <div
        className="hidden md:block border-r border-slate-200 bg-slate-50/40 overflow-auto"
        style={{ width: 140 }}
      >
        <div className="px-3 py-2 text-xs font-bold text-slate-500 border-b border-slate-200/80 bg-white">
          Files
        </div>
        {files.length === 0 && (
          <p className="px-3 py-2.5 text-xs text-slate-400">No files</p>
        )}
        <div className="py-1">
          {files.map((f) => (
            <button
              key={f.path}
              onClick={() => openFile(f.path)}
              className={`w-full text-left flex items-center gap-1.5 px-3 py-2 text-xs truncate transition-colors ${
                activeFile === f.path 
                  ? 'bg-indigo-50 text-indigo-755 text-indigo-700 font-bold border-r-2 border-indigo-650' 
                  : 'text-slate-655 text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              }`}
              title={f.path}
            >
              <FileText className="w-3.5 h-3.5 shrink-0 text-slate-400" />
              <span className="truncate">{f.path}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Editor - ~55% on desktop, stacked on mobile */}
      <div className="flex flex-col w-full md:w-[55%] h-1/2 md:h-auto border-r border-slate-200">
        <div className="h-12 border-b border-slate-200 bg-slate-50/50 flex items-center justify-between px-4">
          <span className="text-xs font-semibold text-slate-700 truncate">{activeFile || 'No file open'}</span>
          {activeFile && (
            <div className="flex items-center gap-3">
              {saveStatus === 'success' && (
                <span className="text-[10px] font-bold text-emerald-600 bg-emerald-50 border border-emerald-250 px-2.5 py-0.5 rounded-full">Saved!</span>
              )}
              {saveStatus === 'error' && (
                <span className="text-[10px] font-bold text-rose-600 bg-rose-50 border border-rose-250 px-2.5 py-0.5 rounded-full">Save Failed</span>
              )}
              <button
                onClick={saveFile}
                disabled={saving}
                className="flex items-center gap-1.5 text-xs font-bold text-indigo-600 hover:text-indigo-700 disabled:opacity-50 transition-colors"
              >
                <Save className="w-3.5 h-3.5" /> {saving ? 'Saving...' : 'Save File'}
              </button>
            </div>
          )}
        </div>
        <div className="flex-1 min-h-0">
          <Editor
            height="100%"
            language={activeFile ? langFromPath(activeFile) : 'plaintext'}
            value={fileContent}
            onChange={(v) => setFileContent(v ?? '')}
            theme="vs"
            options={{ minimap: { enabled: false }, fontSize: 13 }}
            onMount={handleEditorDidMount}
          />
        </div>
      </div>

      {/* Right panel - ~35% */}
      <div className="flex flex-col bg-white flex-1 min-w-0">
        <div className="h-12 border-b border-slate-200 bg-slate-50/50 flex items-center">
          {([
            { key: 'ai' as TabKey, label: 'AI', icon: Sparkles },
            { key: 'terminal' as TabKey, label: 'Terminal', icon: TerminalSquare },
            { key: 'tunnel' as TabKey, label: 'Tunnel', icon: Link2 },
            { key: 'devlog' as TabKey, label: 'Devlog', icon: BookOpen },
          ]).map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`flex items-center gap-1.5 px-4 h-full text-xs font-semibold border-r border-slate-200 transition-colors ${
                tab === key 
                  ? 'text-indigo-700 bg-white border-b-2 border-b-indigo-600' 
                  : 'text-slate-500 hover:text-indigo-650 hover:bg-slate-100/30'
              }`}
            >
              <Icon className="w-3.5 h-3.5 text-slate-400" /> {label}
            </button>
          ))}
        </div>

        {/* AI tab */}
        {tab === 'ai' && (
          <div className="flex flex-col flex-1 min-h-0 bg-white">
            <div className="flex-1 overflow-auto p-4 space-y-3">
              {messages.length === 0 && (
                <p className="text-xs text-slate-455 text-slate-500 font-semibold text-center py-6">Ask the AI assistant about your code.</p>
              )}
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={`text-xs p-3.5 rounded-2xl border shadow-sm ${
                    m.role === 'user'
                      ? 'border-indigo-150 border-indigo-100 bg-indigo-50/40 text-slate-800 ml-6 rounded-br-none'
                      : 'border-slate-200 bg-slate-50 text-slate-755 text-slate-700 mr-6 rounded-bl-none'
                  }`}
                >
                  {m.text}
                </div>
              ))}
              {aiLoading && (
                <div className="flex items-center gap-2 text-xs text-slate-400 mr-6">
                  <div className="animate-spin rounded-full h-3 w-3 border-t-2 border-indigo-600" />
                  <span>Thinking...</span>
                </div>
              )}
            </div>
            <div className="border-t border-slate-250 border-slate-150 border-slate-200 p-3 flex gap-2">
              <input
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && sendChat()}
                placeholder="Type a message..."
                className="flex-1 text-xs border border-slate-200 rounded-xl px-3 py-2 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-105 focus:ring-indigo-100 transition-colors bg-white text-slate-900"
              />
              <button
                onClick={sendChat}
                className="p-2.5 rounded-xl bg-indigo-600 text-white hover:bg-indigo-700 shadow-md shadow-indigo-500/10 transition-colors"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}

        {/* Terminal tab */}
        {tab === 'terminal' && (
          <div className="flex-1 min-h-0 p-3 bg-slate-50">
            <div ref={termContainerRef} className="w-full h-full bg-white border border-slate-200 rounded-xl overflow-hidden p-2 shadow-inner" />
          </div>
        )}

        {/* Tunnel tab */}
        {tab === 'tunnel' && (
          <div className="flex-1 overflow-auto p-4 space-y-3">
            {tunnels.length === 0 && (
              <p className="text-xs text-slate-455 text-slate-500 font-semibold text-center py-6">No active tunnel for this app.</p>
            )}
            {tunnels.map((t) => {
              const url = `http://${t.subdomain}.quad.localhost:8000`;
              return (
                <div key={t.tunnel_id} className="border border-slate-200 bg-slate-50/50 rounded-xl p-4 shadow-inner">
                  <div className="flex items-center justify-between mb-1.5 gap-2">
                    <span className="font-mono text-slate-800 truncate text-xs font-semibold">{url}</span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                        t.status === 'ACTIVE'
                          ? 'border-emerald-200 text-emerald-700 bg-emerald-50'
                          : 'border-slate-200 text-slate-500 bg-white'
                      }`}
                    >
                      {t.status}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500 font-semibold mb-3">local port {t.local_port}</p>
                  <div className="flex gap-3">
                    <button
                      onClick={() => navigator.clipboard.writeText(url)}
                      className="flex items-center gap-1 text-xs font-bold text-indigo-650 hover:text-indigo-755 hover:text-indigo-700 transition-colors"
                    >
                      <Copy className="w-3 h-3" /> Copy URL
                    </button>
                    <a
                      href={url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-1 text-xs font-bold text-indigo-650 hover:text-indigo-755 hover:text-indigo-700 transition-colors"
                    >
                      <ExternalLink className="w-3 h-3" /> Visit App
                    </a>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Devlog tab */}
        {tab === 'devlog' && (
          <div className="flex-1 overflow-auto p-4 space-y-4">
            {!showLogEditor ? (
              <button
                onClick={() => setShowLogEditor(true)}
                className="text-xs font-bold px-3 py-1.5 rounded-lg border border-indigo-200 text-indigo-700 bg-indigo-50 hover:bg-indigo-100/50 shadow-sm transition-colors"
              >
                Create Devlog Entry
              </button>
            ) : (
              <div className="space-y-3 border border-slate-200 bg-slate-50/50 rounded-xl p-3.5 shadow-inner">
                <input
                  value={logTitle}
                  onChange={(e) => setLogTitle(e.target.value)}
                  placeholder="Entry title"
                  className="w-full text-xs border border-slate-200 bg-white rounded-lg px-3 py-2 text-slate-900 focus:outline-none focus:border-indigo-500"
                />
                <textarea
                  value={logContent}
                  onChange={(e) => setLogContent(e.target.value)}
                  placeholder="What did you build?"
                  className="w-full text-xs border border-slate-200 bg-white rounded-lg px-3 py-2 h-20 text-slate-900 focus:outline-none focus:border-indigo-500"
                />
                <div className="flex gap-2">
                  <button
                    onClick={createDevlog}
                    disabled={logBusy}
                    className="text-xs font-bold px-4 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 shadow-md shadow-indigo-500/10 transition-colors"
                  >
                    {logBusy ? 'Saving...' : 'Save'}
                  </button>
                  <button
                    onClick={() => setShowLogEditor(false)}
                    className="text-xs font-semibold px-4 py-1.5 rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
            {devlogs.length === 0 && (
              <p className="text-xs text-slate-455 text-slate-500 font-semibold text-center py-6">No devlog entries yet.</p>
            )}
            <div className="space-y-3">
              {devlogs.map((d) => (
                <div key={d.log_id} className="border border-slate-200 bg-white rounded-xl p-4 shadow-sm hover:border-slate-300 transition-all">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-bold text-slate-800">{d.title}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-slate-400 font-mono">
                        {new Date(d.created_at).toLocaleDateString()}
                      </span>
                      <button
                        onClick={async () => {
                          if (window.confirm('Are you sure you want to delete this devlog entry?')) {
                            try {
                              await api.delete(`/devlog/${appName}/${d.log_id}`);
                              loadDevlogs();
                            } catch {
                              /* ignore */
                            }
                          }
                        }}
                        className="text-[10px] font-bold text-rose-500 hover:text-rose-600 ml-1.5 transition-colors"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                  <p className="text-xs text-slate-600 mt-2 line-clamp-3 leading-relaxed">
                    {d.content.length > 160 ? `${d.content.slice(0, 160)}...` : d.content}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default DevPanelPage;
