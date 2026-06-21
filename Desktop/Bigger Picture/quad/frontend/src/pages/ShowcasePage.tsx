import React, { useEffect, useState } from 'react';
import { useAuth } from '../lib/auth';
import api from '../lib/api';
import { 
  Compass, 
  Search, 
  ThumbsUp, 
  Eye, 
  GitFork, 
  ExternalLink,
  ShieldAlert,
  ArrowRight,
  User,
  Heart,
  FileText
} from 'lucide-react';
import { Link } from 'react-router-dom';

interface App {
  id: number;
  name: string;
  stack?: string;
  status: string;
  container_id?: string;
  image_tag?: string;
  internal_port?: number;
  max_wake_seconds?: number;
  last_seen?: string;
  created_at: string;
  build_log_path?: string;
  owner?: string;
  visibility: string;
  description?: string;
  tags?: string;
  view_count: number;
  upvote_count: number;
  has_docs?: boolean | number;
}

export const ShowcasePage: React.FC = () => {
  const { user } = useAuth();
  const [apps, setApps] = useState<App[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [selectedTag, setSelectedTag] = useState('');
  
  // Upvoted status tracking per app
  const [myUpvotes, setMyUpvotes] = useState<Record<string, boolean>>({});
  
  // Fork states
  const [forkingApp, setForkingApp] = useState<App | null>(null);
  const [newForkName, setNewForkName] = useState('');
  const [forkError, setForkError] = useState<string | null>(null);
  const [forkingLoading, setForkingLoading] = useState(false);

  const fetchShowcase = async () => {
    try {
      const resp = await api.get('/showcase', {
        params: {
          query: query || undefined,
          tag: selectedTag || undefined,
        },
      });
      setApps(resp.data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const fetchUpvotes = async () => {
    if (!user) return;
    try {
      const resp = await api.get('/social/upvotes');
      const votes: Record<string, boolean> = {};
      for (const appName of resp.data) {
        votes[appName] = true;
      }
      setMyUpvotes(votes);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchShowcase();
  }, [query, selectedTag]);

  useEffect(() => {
    fetchUpvotes();
  }, [user]);

  const recordAppView = async (appName: string) => {
    try {
      await api.post(`/showcase/${appName}/view`);
    } catch (e) {
      // Ignore errors on background log view
    }
  };

  const handleUpvoteToggle = async (appName: string) => {
    if (!user) {
      alert('You must be logged in to upvote applications.');
      return;
    }

    const isUpvoted = myUpvotes[appName];
    try {
      if (isUpvoted) {
        await api.delete(`/social/upvotes/${appName}`);
        setMyUpvotes(prev => ({ ...prev, [appName]: false }));
      } else {
        await api.post(`/social/upvotes/${appName}`);
        setMyUpvotes(prev => ({ ...prev, [appName]: true }));
      }
      fetchShowcase();
    } catch (e: any) {
      const detail = e.response?.data?.detail || 'Upvote action failed.';
      alert(detail);
    }
  };

  const handleForkSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!forkingApp) return;
    setForkError(null);
    setForkingLoading(true);

    try {
      await api.post('/social/forks', {
        original_app: forkingApp.name,
        forked_app: newForkName,
      });
      setForkingApp(null);
      setNewForkName('');
      alert('Fork successfully initiated! You will be redirected to the dashboard.');
      window.location.href = '/dashboard';
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.response?.data?.error || 'Fork failed.';
      setForkError(msg);
    } finally {
      setForkingLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Public Project Showcase</h1>
          <p className="text-slate-500 text-sm">Discover and fork projects created by fellow students</p>
        </div>

        {/* Search */}
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-3 top-3 w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search projects..."
            className="w-full bg-white border border-slate-200 rounded-xl py-2 pl-10 pr-4 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-indigo-500 transition-colors"
          />
        </div>
      </div>

      {/* Tags Filter */}
      <div className="flex items-center gap-2 flex-wrap text-xs">
        <span className="text-slate-500 font-semibold uppercase tracking-wider mr-1">Filter Tags:</span>
        {['', 'frontend', 'backend', 'database', 'react', 'python', 'node'].map((tag) => (
          <button
            key={tag}
            onClick={() => setSelectedTag(tag)}
            className={`px-3 py-1.5 rounded-full border transition-all ${
              selectedTag === tag
                ? 'bg-indigo-50 border-indigo-200 text-indigo-700 font-semibold shadow-sm'
                : 'bg-white border-slate-200 text-slate-500 hover:text-slate-800 hover:bg-slate-50'
            }`}
          >
            {tag === '' ? 'All Projects' : `#${tag}`}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-indigo-650 border-indigo-650/30" />
        </div>
      ) : apps.length === 0 ? (
        <div className="border border-dashed border-slate-200 p-12 text-center rounded-2xl bg-white">
          <Compass className="w-10 h-10 text-slate-400 mx-auto mb-3" />
          <h4 className="font-bold text-slate-700">No public projects found</h4>
          <p className="text-xs text-slate-500 mt-0.5">Be the first to publish your application to the showcase!</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {apps.map((app) => (
            <div 
              key={app.id} 
              className="p-5 rounded-2xl border border-slate-200 bg-white shadow-sm flex flex-col justify-between card-hover transition-all group"
            >
              <div className="space-y-3">
                <div className="flex justify-between items-start gap-2">
                  <div>
                    <h3 className="font-bold text-base text-slate-800 group-hover:text-indigo-600 transition-colors flex items-center gap-1.5">
                      {app.name}
                      {!!app.has_docs && (
                        <span 
                          className="text-indigo-500 cursor-help" 
                          title="AI documentation has been generated for this application"
                        >
                          <FileText className="w-4 h-4 inline" />
                        </span>
                      )}
                    </h3>
                    <Link 
                      to={`/profile?username=${app.owner}`} 
                      className="text-xs text-slate-550 hover:text-indigo-600 font-medium inline-flex items-center gap-1 mt-0.5 transition-colors"
                    >
                      <User className="w-3 h-3 text-slate-400" /> @{app.owner}
                    </Link>
                  </div>
                  <span className="text-[10px] font-mono bg-slate-50 text-slate-500 px-2 py-0.5 rounded border border-slate-200 uppercase shrink-0">
                    {app.stack || 'static'}
                  </span>
                </div>

                <p className="text-xs text-slate-655 text-slate-500 line-clamp-2 leading-relaxed">
                  {app.description || 'No description provided.'}
                </p>

                {app.tags && (
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {app.tags.split(',').map((t) => (
                      <span key={t} className="text-[10px] text-indigo-600 font-semibold">
                        #{t.trim()}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Card Footer Actions */}
              <div className="pt-4 mt-4 border-t border-slate-100 flex items-center justify-between">
                {/* Stats */}
                <div className="flex items-center gap-3 text-xs text-slate-500">
                  <button 
                    onClick={() => handleUpvoteToggle(app.name)}
                    className="flex items-center gap-1 hover:text-rose-500 transition-colors"
                  >
                    <Heart className={`w-4 h-4 ${myUpvotes[app.name] ? 'fill-rose-500 text-rose-500' : 'text-slate-400'}`} />
                    <span>{app.upvote_count}</span>
                  </button>
                  <div className="flex items-center gap-1">
                    <Eye className="w-4 h-4 text-slate-400" />
                    <span>{app.view_count}</span>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2">
                  {app.status === 'RUNNING' && (
                    <a
                      href={`http://${app.name}.quad.localhost:8000`}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={() => recordAppView(app.name)}
                      className="p-1.5 rounded bg-slate-50 hover:bg-slate-100 text-slate-500 hover:text-slate-700 border border-slate-200 transition-colors"
                      title="Visit application"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  )}

                  {user && user.username !== app.owner && (
                    <button
                      onClick={() => setForkingApp(app)}
                      className="p-1.5 rounded bg-indigo-50 hover:bg-indigo-100 text-indigo-600 border border-indigo-200/50 hover:border-indigo-200 transition-all flex items-center gap-1 text-xs font-semibold"
                      title="Fork project"
                    >
                      <GitFork className="w-3.5 h-3.5" /> Fork
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Fork Modal */}
      {forkingApp && (
        <div className="fixed inset-0 bg-slate-900/45 backdrop-blur-sm flex items-center justify-center p-6 z-50">
          <div className="max-w-md w-full bg-white border border-slate-200 rounded-3xl overflow-hidden shadow-xl p-6 space-y-4">
            <div>
              <h3 className="font-bold text-lg text-slate-800 flex items-center gap-2">
                <GitFork className="w-5 h-5 text-indigo-600" /> Fork Project: {forkingApp.name}
              </h3>
              <p className="text-xs text-slate-500 mt-1">
                Forking copies the project files to your account so you can modify and deploy them
              </p>
            </div>

            {forkError && (
              <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-600 text-xs flex items-start gap-2.5">
                <ShieldAlert className="w-4 h-4 shrink-0" />
                <span>{forkError}</span>
              </div>
            )}

            <form onSubmit={handleForkSubmit} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">New Application Name</label>
                <input
                  type="text"
                  required
                  pattern="[a-z0-9\-]{3,40}"
                  value={newForkName}
                  onChange={(e) => setNewForkName(e.target.value)}
                  placeholder="my-forked-app"
                  className="w-full bg-white border border-slate-200 rounded-xl py-2.5 px-4 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-indigo-500 transition-colors"
                />
              </div>

              <div className="flex gap-3 justify-end pt-2">
                <button
                  type="button"
                  onClick={() => setForkingApp(null)}
                  className="px-4 py-2 text-sm text-slate-500 hover:text-slate-800 font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={forkingLoading}
                  className="bg-indigo-600 hover:bg-indigo-700 px-5 py-2 rounded-xl text-sm font-bold text-white shadow-md shadow-indigo-500/10 flex items-center gap-1.5"
                >
                  {forkingLoading ? 'Forking...' : 'Confirm Fork'} <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
export default ShowcasePage;
