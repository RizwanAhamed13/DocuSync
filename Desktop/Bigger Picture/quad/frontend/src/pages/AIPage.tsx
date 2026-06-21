import React, { useState, useEffect, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { marked } from 'marked';
import mermaid from 'mermaid';
import api from '../lib/api';
import { useAIJob } from '../hooks/useAIJob';
import { JobStatusBanner } from '../components/JobStatusBanner';
import { 
  MessageSquare, 
  Search, 
  FileText, 
  Users, 
  GitBranch, 
  Code, 
  ChevronRight, 
  Send, 
  Play, 
  Check, 
  AlertCircle,
  Copy,
  Download,
  Terminal
} from 'lucide-react';

mermaid.initialize({
  startOnLoad: false,
  theme: 'neutral',
  securityLevel: 'loose',
  themeVariables: {
    background: '#ffffff',
    primaryColor: '#e0e7ff',
    primaryTextColor: '#1e1b4b',
    lineColor: '#6366f1',
  }
});

interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: Array<{
    file_path: string;
    start_line: number;
    end_line: number;
    symbol_name?: string | null;
  }>;
}

// Simple Mermaid diagram component
const MermaidDiagram: React.FC<{ code: string }> = ({ code }) => {
  const ref = useRef<HTMLDivElement>(null);
  const cleanCode = code
    .replace(/^```mermaid\s*/i, '')
    .replace(/```\s*$/i, '')
    .trim();

  useEffect(() => {
    if (ref.current && cleanCode) {
      ref.current.removeAttribute('data-processed');
      ref.current.innerHTML = cleanCode;
      try {
        mermaid.contentLoaded();
      } catch (e) {
        console.error("Mermaid render error:", e);
      }
    }
  }, [cleanCode]);

  return (
    <div 
      ref={ref} 
      className="mermaid flex justify-center p-4 bg-white rounded-xl overflow-x-auto border border-slate-100 shadow-sm my-2"
    />
  );
};

// Component to render chat messages containing markdown and optional inline mermaid diagrams
const MessageContent: React.FC<{ content: string }> = ({ content }) => {
  if (content.includes('```mermaid')) {
    const parts = content.split(/```mermaid/i);
    return (
      <div className="space-y-3 w-full">
        {parts.map((part, idx) => {
          if (idx === 0) {
            return (
              <div
                key={idx}
                className="prose prose-sm max-w-none text-inherit leading-relaxed"
                dangerouslySetInnerHTML={{ __html: marked.parse(part) }}
              />
            );
          }
          const subParts = part.split(/```/);
          const mermaidCode = subParts[0].trim();
          const restText = subParts.slice(1).join('```');
          return (
            <React.Fragment key={idx}>
              <MermaidDiagram code={mermaidCode} />
              {restText.trim() && (
                <div
                  className="prose prose-sm max-w-none text-inherit leading-relaxed mt-2"
                  dangerouslySetInnerHTML={{ __html: marked.parse(restText) }}
                />
              )}
            </React.Fragment>
          );
        })}
      </div>
    );
  }

  return (
    <div 
      className="prose prose-sm max-w-none text-inherit leading-relaxed"
      dangerouslySetInnerHTML={{ __html: marked.parse(content) }}
    />
  );
};

export const AIPage: React.FC = () => {
  const { appName } = useParams<{ appName: string }>();
  const [activeTab, setActiveTab] = useState<'chat' | 'review' | 'docs' | 'onboarding' | 'diagram'>('chat');
  const [indexStatus, setIndexStatus] = useState<{ indexed: boolean; chunk_count: number; file_count: number } | null>(null);
  
  // Job submitters
  const ingestJob = useAIJob();
  const chatJob = useAIJob();
  const reviewJob = useAIJob();
  const docsJob = useAIJob();
  const onboardingJob = useAIJob();
  const diagramJob = useAIJob();

  // Chat states
  const [chatMessages, setChatMessages] = useState<Message[]>([]);
  const [chatInput, setChatInput] = useState('');
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Review states
  const [diffInput, setDiffInput] = useState('');

  // Docs states
  const [docTypeSelected, setDocTypeSelected] = useState<'readme' | 'api' | 'modules'>('readme');

  // Onboarding states
  const [memberRole, setMemberRole] = useState('general');
  const [memberName, setMemberName] = useState('');

  // Copy/Download success helper
  const [copiedText, setCopiedText] = useState(false);

  const fetchIndexStatus = async () => {
    if (!appName) return;
    try {
      const resp = await api.get(`/ai/status/${appName}`);
      setIndexStatus(resp.data);
    } catch (e) {
      console.error(e);
    }
  };

  const fetchChatHistory = async () => {
    if (!appName) return;
    try {
      const resp = await api.get<any[]>(`/ai/jobs?app_name=${appName}&job_type=chat&status=DONE`);
      const historyJobs = [...resp.data].reverse();
      const historyMessages: Message[] = [];
      historyJobs.forEach(job => {
        if (job.input && job.input.question) {
          historyMessages.push({ role: 'user', content: job.input.question });
        }
        if (job.result && job.result.answer) {
          historyMessages.push({
            role: 'assistant',
            content: job.result.answer,
            sources: job.result.sources
          });
         }
      });
      setChatMessages(historyMessages);
    } catch (e) {
      console.error("Error loading chat history:", e);
    }
  };

  useEffect(() => {
    fetchIndexStatus();
    fetchChatHistory();
  }, [appName]);

  // Scroll to bottom of chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, chatJob.status]);

  // Sync index status when ingest completes
  useEffect(() => {
    if (ingestJob.status === 'done') {
      fetchIndexStatus();
    }
  }, [ingestJob.status]);

  // Handle Chat result once complete
  useEffect(() => {
    if (chatJob.status === 'done' && chatJob.result) {
      setChatMessages(prev => [
        ...prev, 
        { 
          role: 'assistant', 
          content: chatJob.result.answer, 
          sources: chatJob.result.sources 
        }
      ]);
    }
  }, [chatJob.status, chatJob.result]);

  const handleIndex = () => {
    if (!appName) return;
    ingestJob.submit(`/ai/ingest/${appName}`, {});
  };

  const handleSendChat = (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim() || !appName) return;

    const userMsg = chatInput;
    setChatMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setChatInput('');

    chatJob.submit(`/ai/chat/${appName}`, {
      question: userMsg,
      history: chatMessages.map(m => ({ role: m.role, content: m.content }))
    });
  };

  const handleReview = () => {
    if (!diffInput.trim() || !appName) return;
    reviewJob.submit(`/ai/review/${appName}`, { diff: diffInput });
  };

  const handleDocs = (type: 'readme' | 'api' | 'modules') => {
    if (!appName) return;
    setDocTypeSelected(type);
    docsJob.submit(`/ai/docs/${appName}`, { doc_type: type });
  };

  const handleOnboarding = () => {
    if (!memberName.trim() || !appName) return;
    onboardingJob.submit(`/ai/onboarding/${appName}`, {
      member_role: memberRole,
      member_name: memberName
    });
  };

  const handleDiagram = () => {
    if (!appName) return;
    diagramJob.submit(`/ai/diagram/${appName}`, {});
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedText(true);
    setTimeout(() => setCopiedText(false), 2000);
  };

  const downloadMarkdown = (content: string, filename: string) => {
    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const getSeverityColor = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'critical': return 'bg-rose-50 border border-rose-200 text-rose-700';
      case 'high': return 'bg-orange-50 border border-orange-205 text-orange-700';
      case 'medium': return 'bg-amber-50 border border-amber-200 text-amber-700';
      case 'low': return 'bg-blue-50 border border-blue-200 text-blue-700';
      default: return 'bg-slate-50 border border-slate-200 text-slate-600';
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      {/* Navigation Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-slate-500 mb-6">
        <Link to="/dashboard" className="hover:text-slate-800 transition-colors">Dashboard</Link>
        <ChevronRight className="w-4 h-4 text-slate-400" />
        <span className="text-slate-800 font-medium">{appName}</span>
        <ChevronRight className="w-4 h-4 text-slate-400" />
        <span className="text-indigo-600 font-semibold uppercase">AI Studio</span>
      </div>

      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-extrabold bg-gradient-to-r from-indigo-650 to-indigo-500 bg-clip-text text-transparent uppercase">
            AI Studio: {appName}
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Asynchronous workspace indexing, chatbot assistant, PR code reviews, and diagrams.
          </p>
        </div>

        {/* Indexing status card */}
        {indexStatus && (
          <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-sm flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <div>
              {indexStatus.indexed ? (
                <div className="text-sm text-slate-655 text-slate-600">
                  <span className="text-emerald-600 font-bold">Indexed</span> —{' '}
                  <span className="text-slate-800 font-semibold">{indexStatus.chunk_count} chunks</span> across{' '}
                  <span className="text-slate-800 font-semibold">{indexStatus.file_count} files</span>
                </div>
              ) : (
                <div className="text-sm text-rose-600 font-bold">Not indexed yet</div>
              )}
            </div>
            <button
              onClick={handleIndex}
              disabled={ingestJob.status === 'queued' || ingestJob.status === 'running'}
              className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
            >
              {indexStatus.indexed ? 'Re-index' : 'Index Codebase'}
            </button>
          </div>
        )}
      </div>

      {ingestJob.status !== 'idle' && (
        <div className="mb-6">
          <JobStatusBanner status={ingestJob.status} error={ingestJob.error} />
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-slate-200 gap-2 mb-8 overflow-x-auto">
        <button
          onClick={() => setActiveTab('chat')}
          className={`flex items-center gap-2 px-5 py-3 border-b-2 text-sm font-semibold transition-all ${
            activeTab === 'chat'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <MessageSquare className="w-4 h-4" /> Chat
        </button>
        <button
          onClick={() => setActiveTab('review')}
          className={`flex items-center gap-2 px-5 py-3 border-b-2 text-sm font-semibold transition-all ${
            activeTab === 'review'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <GitBranch className="w-4 h-4" /> Review Diff
        </button>
        <button
          onClick={() => setActiveTab('docs')}
          className={`flex items-center gap-2 px-5 py-3 border-b-2 text-sm font-semibold transition-all ${
            activeTab === 'docs'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <FileText className="w-4 h-4" /> Auto Docs
        </button>
        <button
          onClick={() => setActiveTab('onboarding')}
          className={`flex items-center gap-2 px-5 py-3 border-b-2 text-sm font-semibold transition-all ${
            activeTab === 'onboarding'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <Users className="w-4 h-4" /> Onboarding
        </button>
        <button
          onClick={() => setActiveTab('diagram')}
          className={`flex items-center gap-2 px-5 py-3 border-b-2 text-sm font-semibold transition-all ${
            activeTab === 'diagram'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <Code className="w-4 h-4" /> Architecture
        </button>
      </div>

      {/* Tab Panels */}
      <div className="bg-white border border-slate-200 rounded-3xl p-6 shadow-sm min-h-[400px]">
        
        {/* Chat Tab */}
        {activeTab === 'chat' && (
          <div className="flex flex-col h-[550px] justify-between">
            {/* Messages Area */}
            <div className="flex-1 overflow-y-auto space-y-4 pr-2 mb-4">
              {chatMessages.length === 0 && (
                <div className="h-full flex flex-col items-center justify-center text-center p-8">
                  <div className="w-12 h-12 rounded-xl bg-indigo-50 border border-indigo-200 text-indigo-600 flex items-center justify-center mb-4">
                    <MessageSquare className="w-6 h-6" />
                  </div>
                  <h3 className="font-bold text-lg text-slate-800">Codebase Chat Assistant</h3>
                  <p className="text-slate-500 text-sm max-w-sm mt-1">
                    Ask questions about components, endpoints, libraries, or codebase files. Only uses indexed code context.
                  </p>
                </div>
              )}
              {chatMessages.map((msg, i) => (
                <div 
                  key={i} 
                  className={`flex flex-col max-w-[80%] ${
                    msg.role === 'user' ? 'ml-auto items-end' : 'mr-auto items-start'
                  }`}
                >
                  <div className={`p-4 rounded-2xl text-sm ${
                    msg.role === 'user' 
                      ? 'bg-indigo-600 text-white rounded-br-none' 
                      : 'bg-slate-50 border border-slate-200 text-slate-800 rounded-bl-none w-full'
                  }`}>
                    {msg.role === 'user' ? msg.content : <MessageContent content={msg.content} />}
                  </div>
                  
                  {/* Sources Chips */}
                  {msg.sources && msg.sources.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {msg.sources.map((s, idx) => (
                        <Link 
                          key={idx} 
                          to={`/dev/${appName}?file=${encodeURIComponent(s.file_path)}&line=${s.start_line}`}
                          className="text-xs bg-white border border-slate-200 px-2.5 py-1 rounded-lg text-indigo-650 text-indigo-600 hover:text-indigo-850 hover:bg-indigo-50/50 hover:border-indigo-200 transition-all flex items-center gap-1 cursor-pointer font-semibold shadow-sm"
                          title={s.symbol_name ? `Symbol: ${s.symbol_name}` : undefined}
                        >
                          📄 {s.file_path.split('/').pop()} lines {s.start_line}-{s.end_line}
                        </Link>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              
              {/* Thinking state */}
              {chatJob.status === 'running' && (
                <div className="flex flex-col items-start mr-auto max-w-[80%]">
                  <div className="p-4 bg-slate-50 border border-slate-200 text-slate-500 rounded-2xl rounded-bl-none flex items-center gap-2">
                    <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    <span className="text-xs ml-1">Thinking...</span>
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
            
            {/* Input Form */}
            <form onSubmit={handleSendChat} className="flex gap-2 border-t border-slate-100 pt-4">
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder={indexStatus?.indexed ? "Ask a question about the code..." : "Ingest the codebase first to start chat"}
                disabled={!indexStatus?.indexed || chatJob.status === 'running'}
                className="flex-1 bg-white border border-slate-200 rounded-xl py-3 px-4 text-sm focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-slate-900 placeholder-slate-400 transition-colors disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={!chatInput.trim() || chatJob.status === 'running'}
                className="bg-indigo-600 hover:bg-indigo-700 text-white p-3 rounded-xl transition-colors disabled:opacity-50 flex items-center justify-center shadow-md shadow-indigo-500/10"
              >
                <Send className="w-5 h-5" />
              </button>
            </form>
          </div>
        )}

        {/* Review Tab */}
        {activeTab === 'review' && (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-bold text-slate-800">Asynchronous Diff Code Review</h3>
              <p className="text-slate-500 text-xs mt-0.5">
                Paste unified git diff outputs to diagnose code safety, style inconsistencies, and error handling.
              </p>
            </div>

            <textarea
              value={diffInput}
              onChange={(e) => setDiffInput(e.target.value)}
              placeholder="git diff main..feature-branch | pbcopy"
              className="w-full h-40 bg-white border border-slate-200 rounded-xl p-4 text-xs font-mono text-slate-900 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
            />

            <button
              onClick={handleReview}
              disabled={!diffInput.trim() || reviewJob.status === 'queued' || reviewJob.status === 'running'}
              className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-sm px-6 py-2.5 rounded-xl transition-colors disabled:opacity-50 flex items-center gap-2 shadow-md shadow-indigo-500/10"
            >
              <Play className="w-4 h-4 fill-white" /> Submit for Review
            </button>

            <JobStatusBanner status={reviewJob.status} error={reviewJob.error} />

            {reviewJob.status === 'done' && reviewJob.result && (
              <div className="mt-8 space-y-6 border-t border-slate-100 pt-6">
                {/* Approval Banner */}
                <div className={`p-4 rounded-xl border flex items-center gap-3 ${
                  reviewJob.result.approved 
                    ? 'bg-emerald-50 border-emerald-200 text-emerald-700' 
                    : 'bg-rose-50 border-rose-200 text-rose-700'
                }`}>
                  {reviewJob.result.approved ? (
                    <Check className="w-5 h-5" />
                  ) : (
                    <AlertCircle className="w-5 h-5" />
                  )}
                  <div>
                    <span className="font-bold">{reviewJob.result.approved ? 'Approved' : 'Changes Requested'}</span>
                    <p className="text-xs mt-0.5 opacity-90">{reviewJob.result.approval_reason}</p>
                  </div>
                </div>

                {/* Summary Assessment */}
                <div>
                  <h4 className="font-bold text-sm mb-1 text-slate-800">Review Summary</h4>
                  <p className="text-slate-655 text-slate-600 text-sm leading-relaxed">{reviewJob.result.summary}</p>
                </div>

                {/* Issues List */}
                {reviewJob.result.issues && reviewJob.result.issues.length > 0 && (
                  <div>
                    <h4 className="font-bold text-sm mb-3 text-slate-800">Issues Detected</h4>
                    <div className="space-y-4">
                      {reviewJob.result.issues.map((issue: any, idx: number) => (
                        <div key={idx} className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex flex-col gap-2 shadow-sm">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-mono text-slate-550">
                              {issue.file} {issue.line ? `(line ${issue.line})` : ''}
                            </span>
                            <span className={`text-[10px] uppercase font-bold tracking-wider px-2.5 py-0.5 rounded-full border ${getSeverityColor(issue.severity)}`}>
                              {issue.severity}
                            </span>
                          </div>
                          <p className="text-sm font-semibold text-slate-800">{issue.issue}</p>
                          <div className="p-3 bg-slate-950 rounded-lg border border-slate-900 text-xs font-mono text-slate-350 flex items-start gap-2 shadow-inner">
                            <Terminal className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                            <span>Suggestion: {issue.suggestion}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Docs Tab */}
        {activeTab === 'docs' && (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-bold text-slate-800">Auto-Documentation Generator</h3>
              <p className="text-slate-500 text-xs mt-0.5">
                Generate project READMEs, API endpoints index, or structural modules overview using indexed codebase files.
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <button
                onClick={() => handleDocs('readme')}
                disabled={docsJob.status === 'queued' || docsJob.status === 'running'}
                className="bg-white hover:bg-slate-50 border border-slate-200 font-semibold text-sm px-4 py-2 rounded-xl text-slate-700 hover:text-slate-900 shadow-sm transition-colors disabled:opacity-50"
              >
                Generate README
              </button>
              <button
                onClick={() => handleDocs('api')}
                disabled={docsJob.status === 'queued' || docsJob.status === 'running'}
                className="bg-white hover:bg-slate-50 border border-slate-200 font-semibold text-sm px-4 py-2 rounded-xl text-slate-700 hover:text-slate-900 shadow-sm transition-colors disabled:opacity-50"
              >
                Generate API Docs
              </button>
              <button
                onClick={() => handleDocs('modules')}
                disabled={docsJob.status === 'queued' || docsJob.status === 'running'}
                className="bg-white hover:bg-slate-50 border border-slate-200 font-semibold text-sm px-4 py-2 rounded-xl text-slate-700 hover:text-slate-900 shadow-sm transition-colors disabled:opacity-50"
              >
                Generate Module Docs
              </button>
            </div>

            <JobStatusBanner status={docsJob.status} error={docsJob.error} />

            {docsJob.status === 'done' && docsJob.result && (
              <div className="border-t border-slate-100 pt-6 space-y-4">
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => copyToClipboard(docsJob.result.content)}
                    className="flex items-center gap-1.5 bg-white border border-slate-200 text-xs font-semibold px-3 py-1.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-50 transition-colors shadow-sm"
                  >
                    {copiedText ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                    {copiedText ? 'Copied!' : 'Copy to Clipboard'}
                  </button>
                  <button
                    onClick={() => downloadMarkdown(docsJob.result.content, `${docTypeSelected}-docs.md`)}
                    className="flex items-center gap-1.5 bg-white border border-slate-200 text-xs font-semibold px-3 py-1.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-50 transition-colors shadow-sm"
                  >
                    <Download className="w-3.5 h-3.5" /> Download .md
                  </button>
                </div>
                
                {/* Markdown Renderer Output */}
                <div 
                  className="prose max-w-none p-6 rounded-2xl bg-slate-50 border border-slate-200 text-slate-700 text-sm leading-relaxed"
                  dangerouslySetInnerHTML={{ __html: marked.parse(docsJob.result.content) }}
                />
              </div>
            )}
          </div>
        )}

        {/* Onboarding Tab */}
        {activeTab === 'onboarding' && (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-bold text-slate-800">Onboarding Guide Generator</h3>
              <p className="text-slate-500 text-xs mt-0.5">
                Generate customized workspace onboarding instructions for new team members.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">New Member's Name</label>
                <input
                  type="text"
                  value={memberName}
                  onChange={(e) => setMemberName(e.target.value)}
                  placeholder="Sarah Jenkins"
                  className="w-full bg-white border border-slate-200 rounded-xl py-2.5 px-4 text-sm text-slate-900 focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Role</label>
                <select
                  value={memberRole}
                  onChange={(e) => setMemberRole(e.target.value)}
                  className="w-full bg-white border border-slate-200 rounded-xl py-2.5 px-3 text-sm text-slate-900 focus:outline-none focus:border-indigo-500"
                >
                  <option value="general">General Developer</option>
                  <option value="frontend">Frontend Developer</option>
                  <option value="backend">Backend Developer</option>
                  <option value="fullstack">Fullstack Developer</option>
                  <option value="ml">Machine Learning / Data Eng</option>
                </select>
              </div>
            </div>

            <button
              onClick={handleOnboarding}
              disabled={!memberName.trim() || onboardingJob.status === 'queued' || onboardingJob.status === 'running'}
              className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-sm px-6 py-2.5 rounded-xl transition-colors disabled:opacity-50 shadow-md shadow-indigo-500/10"
            >
              Generate Onboarding Guide
            </button>

            <JobStatusBanner status={onboardingJob.status} error={onboardingJob.error} />

            {onboardingJob.status === 'done' && onboardingJob.result && (
              <div className="border-t border-slate-100 pt-6 space-y-4">
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => copyToClipboard(onboardingJob.result.content)}
                    className="flex items-center gap-1.5 bg-white border border-slate-200 text-xs font-semibold px-3 py-1.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-50 transition-colors shadow-sm"
                  >
                    {copiedText ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                    {copiedText ? 'Copied!' : 'Copy to Clipboard'}
                  </button>
                  <button
                    onClick={() => downloadMarkdown(onboardingJob.result.content, `onboarding-${memberName.toLowerCase().replace(/\s+/g, '-')}.md`)}
                    className="flex items-center gap-1.5 bg-white border border-slate-200 text-xs font-semibold px-3 py-1.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-50 transition-colors shadow-sm"
                  >
                    <Download className="w-3.5 h-3.5" /> Download .md
                  </button>
                </div>
                
                <div 
                  className="prose max-w-none p-6 rounded-2xl bg-slate-50 border border-slate-200 text-slate-700 text-sm leading-relaxed"
                  dangerouslySetInnerHTML={{ __html: marked.parse(onboardingJob.result.content) }}
                />
              </div>
            )}
          </div>
        )}

        {/* Diagram Tab */}
        {activeTab === 'diagram' && (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-bold text-slate-800">Mermaid Architecture Diagram</h3>
              <p className="text-slate-500 text-xs mt-0.5">
                Generate top-down interactive Mermaid architectures linking modules, databases, and dependencies.
              </p>
            </div>

            <button
              onClick={handleDiagram}
              disabled={diagramJob.status === 'queued' || diagramJob.status === 'running'}
              className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-sm px-6 py-2.5 rounded-xl transition-colors disabled:opacity-50 shadow-md shadow-indigo-500/10"
            >
              Generate Diagram
            </button>

            <JobStatusBanner status={diagramJob.status} error={diagramJob.error} />

            {diagramJob.status === 'done' && diagramJob.result && (
              <div className="border-t border-slate-100 pt-6 space-y-4">
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => copyToClipboard(diagramJob.result.diagram)}
                    className="flex items-center gap-1.5 bg-white border border-slate-200 text-xs font-semibold px-3 py-1.5 rounded-lg text-slate-655 text-slate-600 hover:text-slate-900 hover:bg-slate-50 transition-colors shadow-sm"
                  >
                    {copiedText ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                    {copiedText ? 'Copied!' : 'Copy Mermaid Source'}
                  </button>
                </div>

                <MermaidDiagram code={diagramJob.result.diagram} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default AIPage;
