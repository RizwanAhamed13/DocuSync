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
      className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-lg border transition-colors ${
        copied
          ? 'bg-green-50 text-green-700 border-green-200'
          : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300 hover:text-gray-900'
      }`}
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
      {label ?? (copied ? 'Copied!' : 'Copy')}
    </button>
  );
}

function TunnelCard({ tunnel, onClose }: { tunnel: Tunnel; onClose: (id: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const publicUrl = `http://${tunnel.subdomain}.quad.localhost:8000`;
  const isOnline = tunnel.status === 'active';
  const lastPing = tunnel.last_ping
    ? new Date(tunnel.last_ping).toLocaleTimeString()
    : 'Never';

  const frpcConfig = `[common]
server_addr = quad.localhost
server_port = 7000

[${tunnel.frpc_name}]
type = http
local_port = ${tunnel.local_port}
custom_domains = ${tunnel.subdomain}.quad.localhost`;

  const connectCmd = `frpc -c frpc.toml`;

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      {/* Top row */}
      <div className="flex items-center gap-4 p-4">
        <div className={`w-2 h-2 rounded-full shrink-0 ${isOnline ? 'bg-green-500' : 'bg-gray-300'}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-sm text-gray-900">{tunnel.app_name}</span>
            <span className="text-xs font-mono bg-gray-100 text-gray-600 border border-gray-200 px-2 py-0.5 rounded-md">
              :{tunnel.local_port}
            </span>
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${
              isOnline
                ? 'bg-green-50 text-green-700 border-green-200'
                : 'bg-gray-100 text-gray-500 border-gray-200'
            }`}>
              {isOnline ? 'Online' : 'Offline'}
            </span>
          </div>
          <a
            href={publicUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-600 hover:text-blue-700 font-medium inline-flex items-center gap-1 mt-0.5"
          >
            {tunnel.subdomain}.quad.localhost <ExternalLink size={10} />
          </a>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <CopyButton text={publicUrl} label="URL" />
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-2 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 border border-gray-200 transition-colors"
            title={expanded ? 'Collapse' : 'Setup guide'}
          >
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
          <button
            onClick={() => onClose(tunnel.tunnel_id)}
            className="p-2 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 border border-gray-200 hover:border-red-200 transition-colors"
            title="Close tunnel"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {/* Expanded: setup guide */}
      {expanded && (
        <div className="border-t border-gray-200 bg-gray-50 p-4 space-y-4">
          <div className="flex items-center gap-1.5 text-xs text-gray-500 font-medium">
            <Info size={12} /> frp client setup — run on your local machine
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-semibold text-gray-700">1. frpc.toml config file</span>
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
                  className="inline-flex items-center gap-1 text-xs font-medium text-gray-600 bg-white border border-gray-200 px-2.5 py-1.5 rounded-lg hover:border-gray-300 transition-colors"
                >
                  <Download size={12} /> Download
                </button>
              </div>
            </div>
            <pre className="bg-gray-900 text-green-400 text-[11px] font-mono rounded-lg p-3 overflow-x-auto leading-relaxed whitespace-pre">
              {frpcConfig}
            </pre>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-semibold text-gray-700">2. Start the tunnel</span>
              <CopyButton text={connectCmd} />
            </div>
            <div className="bg-gray-900 text-green-400 text-[11px] font-mono rounded-lg p-3 flex items-center justify-between">
              <span>$ {connectCmd}</span>
            </div>
          </div>

          <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-xs text-blue-800 space-y-1">
            <p className="font-semibold">Don't have frp installed?</p>
            <p>
              Download from{' '}
              <span className="font-mono">github.com/fatedier/frp/releases</span> — pick the binary
              for your OS, place frpc next to frpc.toml and run the command above.
            </p>
          </div>

          <div className="flex items-center gap-3 text-xs text-gray-500 pt-1">
            <span>Last ping: {lastPing}</span>
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
          <h1 className="text-xl font-bold text-gray-900">Tunnel Relay</h1>
          <p className="text-sm text-gray-500 mt-0.5">Expose local services to the internet via frp</p>
        </div>
        <button
          onClick={fetchTunnels}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-600 hover:text-gray-900 bg-white border border-gray-200 hover:border-gray-300 rounded-lg px-3 py-2 transition-colors"
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Total tunnels', value: tunnels.length },
          { label: 'Online', value: online, green: true },
          { label: 'Offline', value: tunnels.length - online },
        ].map((s) => (
          <div key={s.label} className="bg-white border border-gray-200 rounded-xl p-4">
            <p className="text-xs text-gray-500 font-medium mb-1">{s.label}</p>
            <p className={`text-2xl font-bold ${s.green ? 'text-green-600' : 'text-gray-900'}`}>{s.value}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Create form */}
        <div className="space-y-4">
          <div className="bg-white border border-gray-200 rounded-2xl p-5">
            <h2 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
              <Plus size={16} className="text-blue-600" /> Open New Tunnel
            </h2>

            {error && (
              <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm flex items-start gap-2">
                <ShieldAlert size={14} className="shrink-0 mt-0.5" />
                {error}
              </div>
            )}

            <form onSubmit={handleOpenTunnel} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1.5">App / Service name</label>
                <input
                  type="text"
                  required
                  value={appName}
                  onChange={(e) => setAppName(e.target.value)}
                  placeholder="my-app"
                  className="w-full bg-white border border-gray-200 rounded-lg px-3 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1.5">Local port</label>
                <input
                  type="number"
                  required
                  min="1"
                  max="65535"
                  value={localPort}
                  onChange={(e) => setLocalPort(e.target.value ? Number(e.target.value) : '')}
                  placeholder="3000"
                  className="w-full bg-white border border-gray-200 rounded-lg px-3 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition"
                />
              </div>
              <button
                type="submit"
                disabled={submitting}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2.5 rounded-lg text-sm transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
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
          <div className="bg-white border border-gray-200 rounded-2xl p-5">
            <h3 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
              <Terminal size={14} className="text-gray-400" /> How it works
            </h3>
            <ol className="space-y-2.5 text-xs text-gray-600 leading-relaxed">
              <li className="flex gap-2"><span className="font-bold text-blue-600 shrink-0">1.</span> Enter your app name and the local port your service runs on.</li>
              <li className="flex gap-2"><span className="font-bold text-blue-600 shrink-0">2.</span> Click Open Tunnel — a subdomain and frp config are generated.</li>
              <li className="flex gap-2"><span className="font-bold text-blue-600 shrink-0">3.</span> Download and run the frpc config on your local machine.</li>
              <li className="flex gap-2"><span className="font-bold text-blue-600 shrink-0">4.</span> Your service is now accessible at the public subdomain URL.</li>
            </ol>
          </div>
        </div>

        {/* Tunnels list */}
        <div className="lg:col-span-2 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-gray-900 flex items-center gap-2">
              <Wifi size={16} className="text-gray-400" /> Active Tunnels
            </h2>
            <span className="text-xs text-gray-500">{tunnels.length} total · auto-refreshes every 10s</span>
          </div>

          {/* Success banner after creation */}
          {createdTunnel && (
            <div className="bg-green-50 border border-green-200 rounded-xl p-4 space-y-3">
              <div className="flex items-center gap-2">
                <div className="w-5 h-5 rounded-full bg-green-600 flex items-center justify-center">
                  <Check size={11} className="text-white" />
                </div>
                <span className="font-semibold text-green-800 text-sm">Tunnel opened successfully!</span>
              </div>
              <div className="grid gap-2">
                <div className="flex items-center justify-between bg-white border border-green-200 rounded-lg px-3 py-2">
                  <span className="text-xs text-gray-600 font-mono truncate">{createdTunnel.public_url}</span>
                  <div className="flex gap-1.5 ml-3 shrink-0">
                    <CopyButton text={createdTunnel.public_url} label="Copy URL" />
                    <a href={createdTunnel.public_url} target="_blank" rel="noopener noreferrer"
                      className="p-1.5 rounded-lg text-gray-500 hover:text-blue-600 border border-gray-200 hover:border-blue-200 transition-colors">
                      <ExternalLink size={12} />
                    </a>
                  </div>
                </div>
                <div className="flex items-center justify-between bg-white border border-green-200 rounded-lg px-3 py-2">
                  <span className="text-xs text-gray-600 font-mono">{createdTunnel.connect_command}</span>
                  <CopyButton text={createdTunnel.connect_command} />
                </div>
              </div>
              <button onClick={() => setCreatedTunnel(null)} className="text-xs text-green-700 hover:underline">Dismiss</button>
            </div>
          )}

          {loading ? (
            <div className="h-40 flex items-center justify-center">
              <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : tunnels.length === 0 ? (
            <div className="bg-white border border-gray-200 rounded-2xl p-12 text-center">
              <div className="w-12 h-12 rounded-xl bg-gray-100 flex items-center justify-center mx-auto mb-4">
                <WifiOff size={22} className="text-gray-400" />
              </div>
              <h3 className="font-semibold text-gray-900 mb-1">No tunnels open</h3>
              <p className="text-sm text-gray-500">Open a tunnel to expose a local port to the internet.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {tunnels.map((t) => (
                <TunnelCard key={t.id} tunnel={t} onClose={handleCloseTunnel} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
export default TunnelPage;
