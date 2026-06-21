import React, { useEffect, useState } from 'react';
import { useAuth } from '../lib/auth';
import api from '../lib/api';
import {
  Globe,
  Plus,
  Trash2,
  Copy,
  Check,
  ExternalLink,
  ShieldAlert,
  RefreshCw,
  Terminal,
  Download,
  Wifi,
  WifiOff,
  ChevronDown,
  ChevronUp,
  Info,
} from 'lucide-react';

interface Tunnel {
  id: number;
  tunnel_id: string;
  app_name: string;
  owner: string;
  local_port: number;
  subdomain: string;
  status: string;
  frpc_name: string;
  created_at: string;
  last_ping?: string;
  bandwidth_in?: number;
  bandwidth_out?: number;
  cur_conns?: number;
}

interface TunnelResult {
  tunnel_id: string;
  subdomain: string;
  public_url: string;
  frpc_config: string;
  connect_command: string;
}

function CopyButton({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={handleCopy}
      className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1.5 rounded-lg border transition-colors shadow-sm ${
        copied
          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
          : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50 hover:border-slate-300 hover:text-slate-900'
      }`}
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
      {label ?? (copied ? 'Copied!' : 'Copy')}
    </button>
  );
}

function TunnelCard({ 
  tunnel, 
  onClose, 
  onRefresh 
}: { 
  tunnel: Tunnel; 
  onClose: (id: string) => void; 
  onRefresh: () => void; 
}) {
  const [expanded, setExpanded] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const publicUrl = `http://${tunnel.subdomain}.quad.localhost:8000`;
  const isOnline = tunnel.status === 'active';
  const lastPing = tunnel.last_ping
    ? new Date(tunnel.last_ping).toLocaleTimeString()
    : 'Never';

  const handleVerify = async () => {
    setVerifying(true);
    try {
      await api.get(`/tunnels/${tunnel.tunnel_id}/ping`);
      onRefresh();
    } catch (e) {
      console.error(e);
    } finally {
      setVerifying(false);
    }
  };

  const formatBytes = (bytes?: number) => {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const frpcConfig = `[common]
server_addr = quad.localhost
server_port = 7000

[${tunnel.frpc_name}]
type = http
local_port = ${tunnel.local_port}
custom_domains = ${tunnel.subdomain}.quad.localhost`;

  const connectCmd = `frpc -c frpc.toml`;

  return (
    <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm hover:border-slate-350 transition-all">
      {/* Top row */}
      <div className="flex items-center gap-4 p-4">
        <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${isOnline ? 'bg-emerald-500 animate-pulse' : 'bg-slate-300'}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-extrabold text-sm text-slate-800">{tunnel.app_name}</span>
            <span className="text-xs font-mono bg-slate-50 text-slate-650 border border-slate-200 px-2 py-0.5 rounded-lg font-bold">
              :{tunnel.local_port}
            </span>
            <span className={`text-xs font-extrabold px-2.5 py-0.5 rounded-full border ${
              isOnline
                ? 'bg-emerald-50 text-emerald-700 border-emerald-250'
                : 'bg-slate-100 text-slate-500 border-slate-200'
            }`}>
              {isOnline ? 'Online' : 'Offline'}
            </span>
          </div>
          <a
            href={publicUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-indigo-650 hover:text-indigo-750 font-bold inline-flex items-center gap-1 mt-1 transition-colors"
          >
            {tunnel.subdomain}.quad.localhost <ExternalLink size={10} />
          </a>
          
          {isOnline && (
            <div className="flex items-center gap-3 mt-2 text-[10px] text-slate-500 font-semibold bg-slate-50 border border-slate-200/60 rounded-xl px-3 py-1.5 w-fit">
              <span className="flex items-center gap-1">
                Conns: <strong className="text-slate-850">{tunnel.cur_conns ?? 0}</strong>
              </span>
              <span className="text-slate-300">|</span>
              <span className="flex items-center gap-1">
                In: <strong className="text-slate-850">{formatBytes(tunnel.bandwidth_in)}</strong>
              </span>
              <span className="text-slate-300">|</span>
              <span className="flex items-center gap-1">
                Out: <strong className="text-slate-850">{formatBytes(tunnel.bandwidth_out)}</strong>
              </span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <CopyButton text={publicUrl} label="URL" />
          <button
            onClick={handleVerify}
            disabled={verifying}
            className="p-2 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-slate-50 border border-slate-200 transition-colors shadow-sm disabled:opacity-40"
            title="Verify Status"
          >
            <Wifi size={14} className={verifying ? 'animate-spin text-indigo-600' : ''} />
          </button>
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-2 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-50 border border-slate-200 transition-colors shadow-sm"
            title={expanded ? 'Collapse' : 'Setup guide'}
          >
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
          <button
            onClick={() => onClose(tunnel.tunnel_id)}
            className="p-2 rounded-lg text-slate-450 hover:text-rose-650 hover:bg-rose-50 border border-slate-200 hover:border-rose-200 transition-colors shadow-sm"
            title="Close tunnel"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {/* Expanded: setup guide */}
      {expanded && (
        <div className="border-t border-slate-200 bg-slate-50/50 p-5 space-y-4">
          <div className="flex items-center gap-1.5 text-xs text-slate-500 font-semibold">
            <Info size={12} /> frp client setup — run on your local machine
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-bold text-slate-700">1. frpc.toml config file</span>
              <div className="flex gap-1.5">
                <CopyButton text={frpcConfig} label="Copy" />
                <button
                  onClick={() => {
                    const blob = new Blob([frpcConfig], { type: 'text/plain' });
                    const a = document.createElement('a');
                    a.href = URL.createObjectURL(blob);
                    a.download = 'frpc.toml';
                    a.click();
                  }}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-655 text-slate-600 bg-white border border-slate-200 px-2.5 py-1.5 rounded-lg hover:border-slate-300 hover:bg-slate-50 shadow-sm transition-colors"
                >
                  <Download size={12} /> Download
                </button>
              </div>
            </div>
            <pre className="bg-slate-950 text-emerald-400 text-[11px] font-mono rounded-xl p-4 overflow-x-auto leading-relaxed whitespace-pre shadow-inner">
              {frpcConfig}
            </pre>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-bold text-slate-700">2. Start the tunnel</span>
              <CopyButton text={connectCmd} />
            </div>
            <div className="bg-slate-950 text-emerald-400 text-[11px] font-mono rounded-xl p-4 flex items-center justify-between shadow-inner">
              <span>$ {connectCmd}</span>
            </div>
          </div>

          <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 text-xs text-indigo-800 space-y-1 leading-relaxed">
            <p className="font-bold">Don't have frp installed?</p>
            <p>
              Download from{' '}
              <a href="https://github.com/fatedier/frp/releases" target="_blank" rel="noreferrer" className="underline font-semibold">
                github.com/fatedier/frp/releases
              </a> — pick the binary for your OS, place frpc next to frpc.toml and run the command above.
            </p>
          </div>

          <div className="flex items-center gap-3 text-[11px] text-slate-500 pt-1 font-semibold">
            <span>Last ping: {lastPing}</span>
            <span>•</span>
            <span>Created: {new Date(tunnel.created_at).toLocaleString()}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export const TunnelPage: React.FC = () => {
  const { user } = useAuth();
  const [tunnels, setTunnels] = useState<Tunnel[]>([]);
  const [loading, setLoading] = useState(true);
  const [appName, setAppName] = useState('');
  const [localPort, setLocalPort] = useState<number | ''>('');
  const [createdTunnel, setCreatedTunnel] = useState<TunnelResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTunnels = async () => {
    try {
      const resp = await api.get('/tunnels', {
        params: user ? { owner: user.username } : {},
      });
      setTunnels(resp.data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTunnels();
    const interval = setInterval(fetchTunnels, 10000);
    return () => clearInterval(interval);
  }, [user]);

  const handleOpenTunnel = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    setCreatedTunnel(null);
    try {
      if (!localPort || localPort < 1 || localPort > 65535) {
        throw new Error('Local port must be 1–65535.');
      }
      const resp = await api.post('/tunnels/open', {
        app_name: appName,
        local_port: Number(localPort),
      });
      setCreatedTunnel(resp.data);
      setAppName('');
      setLocalPort('');
      fetchTunnels();
    } catch (err: any) {
      const msg =
        err.response?.data?.detail || err.response?.data?.error || err.message || 'Failed to open tunnel.';
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleCloseTunnel = async (tunnelId: string) => {
    if (!window.confirm('Close this tunnel?')) return;
    try {
      await api.post(`/tunnels/${tunnelId}/close`);
      fetchTunnels();
    } catch {
      alert('Failed to close tunnel.');
    }
  };

  const online = tunnels.filter((t) => t.status === 'active').length;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">Tunnel Relay</h1>
          <p className="text-sm text-slate-500 mt-0.5">Expose local services to the internet via frp</p>
        </div>
        <button
          onClick={fetchTunnels}
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-slate-655 text-slate-600 hover:text-slate-900 hover:bg-slate-50 bg-white border border-slate-200 hover:border-slate-350 rounded-xl px-4 py-2 transition-colors shadow-sm"
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Total Tunnels', value: tunnels.length },
          { label: 'Online Tunnels', value: online, green: true },
          { label: 'Offline Tunnels', value: tunnels.length - online },
        ].map((s) => (
          <div key={s.label} className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
            <p className="text-xs text-slate-500 font-bold uppercase tracking-wider mb-1">{s.label}</p>
            <p className={`text-2xl font-black ${s.green ? 'text-emerald-600' : 'text-slate-900'}`}>{s.value}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Create form */}
        <div className="space-y-4">
          <div className="bg-white border border-slate-200 rounded-3xl p-6 shadow-sm">
            <h2 className="font-bold text-slate-800 mb-4 flex items-center gap-2">
              <Plus size={16} className="text-indigo-650" /> Open New Tunnel
            </h2>

            {error && (
              <div className="mb-4 p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-600 text-xs flex items-start gap-2.5">
                <ShieldAlert size={14} className="shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleOpenTunnel} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5">App / Service Name</label>
                <input
                  type="text"
                  required
                  value={appName}
                  onChange={(e) => setAppName(e.target.value)}
                  placeholder="my-app"
                  className="w-full bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-colors"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5">Local Port</label>
                <input
                  type="number"
                  required
                  min="1"
                  max="65535"
                  value={localPort}
                  onChange={(e) => setLocalPort(e.target.value ? Number(e.target.value) : '')}
                  placeholder="3000"
                  className="w-full bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-colors"
                />
              </div>
              <button
                type="submit"
                disabled={submitting}
                className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2.5 rounded-xl text-sm transition-colors disabled:opacity-50 flex items-center justify-center gap-2 shadow-md shadow-indigo-500/10"
              >
                {submitting ? (
                  <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> Opening…</>
                ) : (
                  <><Globe size={14} /> Open Tunnel</>
                )}
              </button>
            </form>
          </div>

          {/* How it works */}
          <div className="bg-white border border-slate-200 rounded-3xl p-6 shadow-sm">
            <h3 className="text-sm font-bold text-slate-800 mb-3 flex items-center gap-2">
              <Terminal size={14} className="text-slate-400" /> How it works
            </h3>
            <ol className="space-y-2.5 text-xs text-slate-600 leading-relaxed">
              <li className="flex gap-2"><span className="font-bold text-indigo-650 shrink-0">1.</span> Enter your app name and the local port your service runs on.</li>
              <li className="flex gap-2"><span className="font-bold text-indigo-650 shrink-0">2.</span> Click Open Tunnel — a subdomain and frp config are generated.</li>
              <li className="flex gap-2"><span className="font-bold text-indigo-650 shrink-0">3.</span> Download and run the frpc config on your local machine.</li>
              <li className="flex gap-2"><span className="font-bold text-indigo-650 shrink-0">4.</span> Your service is now accessible at the public subdomain URL.</li>
            </ol>
          </div>
        </div>

        {/* Tunnels list */}
        <div className="lg:col-span-2 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-bold text-slate-800 flex items-center gap-2">
              <Wifi size={16} className="text-slate-400" /> Active Tunnels
            </h2>
            <span className="text-[11px] text-slate-500 font-semibold">{tunnels.length} total · auto-refreshes every 10s</span>
          </div>

          {/* Success banner after creation */}
          {createdTunnel && (
            <div className="bg-emerald-50 border border-emerald-250 border-emerald-200 rounded-2xl p-5 space-y-3">
              <div className="flex items-center gap-2">
                <div className="w-5 h-5 rounded-full bg-emerald-600 flex items-center justify-center">
                  <Check size={11} className="text-white" />
                </div>
                <span className="font-bold text-emerald-800 text-sm">Tunnel opened successfully!</span>
              </div>
              <div className="grid gap-2">
                <div className="flex items-center justify-between bg-white border border-emerald-200 rounded-xl px-4 py-2">
                  <span className="text-xs text-slate-655 text-slate-700 font-mono truncate">{createdTunnel.public_url}</span>
                  <div className="flex gap-1.5 ml-3 shrink-0">
                    <CopyButton text={createdTunnel.public_url} label="Copy URL" />
                    <a href={createdTunnel.public_url} target="_blank" rel="noopener noreferrer"
                      className="p-1.5 rounded-lg text-slate-500 hover:text-indigo-600 border border-slate-200 hover:border-indigo-200 bg-white shadow-sm transition-colors">
                      <ExternalLink size={12} />
                    </a>
                  </div>
                </div>
                <div className="flex items-center justify-between bg-white border border-emerald-200 rounded-xl px-4 py-2">
                  <span className="text-xs text-slate-655 text-slate-700 font-mono">{createdTunnel.connect_command}</span>
                  <CopyButton text={createdTunnel.connect_command} />
                </div>
              </div>
              <button onClick={() => setCreatedTunnel(null)} className="text-xs text-emerald-800 font-bold hover:underline">Dismiss Banner</button>
            </div>
          )}

          {loading ? (
            <div className="h-40 flex items-center justify-center">
              <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : tunnels.length === 0 ? (
            <div className="bg-white border border-slate-200 rounded-3xl p-12 text-center shadow-sm">
              <div className="w-12 h-12 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-center mx-auto mb-4">
                <WifiOff size={22} className="text-slate-400" />
              </div>
              <h3 className="font-bold text-slate-800 mb-1">No active tunnels</h3>
              <p className="text-sm text-slate-500">Open a tunnel to expose a local port to the internet.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {tunnels.map((t) => (
                <TunnelCard key={t.id} tunnel={t} onClose={handleCloseTunnel} onRefresh={fetchTunnels} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
export default TunnelPage;
