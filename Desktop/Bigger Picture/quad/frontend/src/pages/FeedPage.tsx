import React, { useEffect, useState, useCallback } from 'react';
import api from '../lib/api';
import { useAuth } from '../lib/auth';
import { Heart, MessageCircle, Code2, Send } from 'lucide-react';

interface Post {
  post_id: string;
  username: string;
  display_name: string;
  avatar_initial: string;
  content: string;
  code_snippet?: string | null;
  language?: string | null;
  project_name?: string | null;
  post_type: string;
  likes_count: number;
  comments_count: number;
  created_at: string;
}

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  const diff = Math.max(0, Date.now() - then);
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export const FeedPage: React.FC = () => {
  const { isAuthenticated } = useAuth();
  const [posts, setPosts] = useState<Post[]>([]);
  const [content, setContent] = useState('');
  const [showCode, setShowCode] = useState(false);
  const [codeSnippet, setCodeSnippet] = useState('');
  const [language, setLanguage] = useState('python');
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters and Comments state
  const [filterType, setFilterType] = useState<'all' | 'text' | 'code' | 'project'>('all');
  const [openComments, setOpenComments] = useState<Record<string, boolean>>({});
  const [postComments, setPostComments] = useState<Record<string, any[]>>({});
  const [commentInputs, setCommentInputs] = useState<Record<string, string>>({});
  const [loadingComments, setLoadingComments] = useState<Record<string, boolean>>({});

  const loadFeed = useCallback(async () => {
    try {
      const resp = await api.get<Post[]>('/feed');
      setPosts(resp.data);
    } catch {
      setError('Failed to load feed');
    }
  }, []);

  useEffect(() => {
    loadFeed();
  }, [loadFeed]);

  const handlePost = async () => {
    if (!content.trim() && !codeSnippet.trim()) return;
    setPosting(true);
    setError(null);
    try {
      await api.post('/feed', {
        content,
        code_snippet: showCode ? codeSnippet : null,
        language: showCode ? language : null,
        post_type: showCode ? 'code' : 'text',
      });
      setContent('');
      setCodeSnippet('');
      setShowCode(false);
      await loadFeed();
    } catch {
      setError('Failed to create post. Are you signed in?');
    } finally {
      setPosting(false);
    }
  };

  const handleLike = async (postId: string) => {
    try {
      const resp = await api.post<{ liked: boolean; likes_count: number }>(
        `/feed/${postId}/like`
      );
      setPosts((prev) =>
        prev.map((p) =>
          p.post_id === postId ? { ...p, likes_count: resp.data.likes_count } : p
        )
      );
    } catch {
      /* ignore */
    }
  };

  const toggleComments = async (postId: string) => {
    const isOpen = !openComments[postId];
    setOpenComments((prev) => ({ ...prev, [postId]: isOpen }));
    if (isOpen) {
      setLoadingComments((prev) => ({ ...prev, [postId]: true }));
      try {
        const resp = await api.get(`/feed/${postId}/comments`);
        setPostComments((prev) => ({ ...prev, [postId]: resp.data }));
      } catch {
        /* ignore */
      } finally {
        setLoadingComments((prev) => ({ ...prev, [postId]: false }));
      }
    }
  };

  const handleAddComment = async (postId: string) => {
    const text = commentInputs[postId]?.trim();
    if (!text) return;
    try {
      const resp = await api.post(`/feed/${postId}/comments`, { content: text });
      setPostComments((prev) => ({
        ...prev,
        [postId]: [...(prev[postId] || []), resp.data],
      }));
      setCommentInputs((prev) => ({ ...prev, [postId]: '' }));
      setPosts((prev) =>
        prev.map((p) =>
          p.post_id === postId ? { ...p, comments_count: p.comments_count + 1 } : p
        )
      );
    } catch {
      /* ignore */
    }
  };

  const filteredPosts = posts.filter((p) => {
    if (filterType === 'text') return p.post_type === 'text';
    if (filterType === 'code') return p.post_type === 'code';
    if (filterType === 'project') return p.post_type === 'project';
    return true;
  });

  return (
    <div className="max-w-2xl mx-auto px-4 py-6">
      <h1 className="text-2xl font-extrabold text-slate-900 mb-6">Community Feed</h1>

      {/* Create post */}
      {isAuthenticated && (
        <div className="bg-white border border-slate-200 rounded-2xl p-5 mb-6 shadow-sm">
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Share something with the community..."
            className="w-full resize-none border border-slate-200 rounded-xl p-3.5 text-sm text-slate-800 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all"
            rows={3}
          />
          {showCode && (
            <div className="mt-3">
              <div className="flex items-center gap-2 mb-1.5">
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="text-xs border border-slate-200 bg-white rounded-lg px-2.5 py-1.5 text-slate-700 focus:outline-none focus:border-indigo-500 transition-colors"
                >
                  <option value="python">Python</option>
                  <option value="javascript">JavaScript</option>
                  <option value="java">Java</option>
                </select>
              </div>
              <textarea
                value={codeSnippet}
                onChange={(e) => setCodeSnippet(e.target.value)}
                placeholder="Paste code snippet..."
                className="w-full resize-none border border-slate-200 rounded-xl p-3.5 text-xs font-mono text-slate-800 focus:outline-none focus:border-indigo-500 bg-slate-50"
                rows={5}
              />
            </div>
          )}
          <div className="flex items-center justify-between mt-4">
            <button
              onClick={() => setShowCode((v) => !v)}
              className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border font-semibold transition-all ${
                showCode
                  ? 'border-indigo-200 text-indigo-700 bg-indigo-50 shadow-sm'
                  : 'border-slate-200 text-slate-500 hover:text-slate-850 hover:bg-slate-50'
              }`}
            >
              <Code2 className="w-3.5 h-3.5" /> Code Snippet
            </button>
            <button
              onClick={handlePost}
              disabled={posting}
              className="flex items-center gap-1.5 text-sm font-bold text-white px-5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 shadow-md shadow-indigo-500/10 transition-colors"
            >
              <Send className="w-3.5 h-3.5" /> Post
            </button>
          </div>
          {error && <p className="text-xs text-rose-500 mt-2 font-semibold">{error}</p>}
        </div>
      )}

      {/* Feed Filters */}
      <div className="flex gap-2 mb-6">
        {(['all', 'text', 'code', 'project'] as const).map((type) => (
          <button
            key={type}
            onClick={() => setFilterType(type)}
            className={`text-xs font-bold px-3.5 py-2 rounded-xl border transition-all ${
              filterType === type
                ? 'border-indigo-200 text-indigo-700 bg-indigo-50/50 shadow-sm'
                : 'border-slate-200 text-slate-500 hover:bg-slate-50'
            }`}
          >
            {type === 'all' ? 'All' : type === 'text' ? 'Text Only' : type === 'code' ? 'Code Snippets' : 'Projects'}
          </button>
        ))}
      </div>

      {/* Feed list */}
      <div className="space-y-4">
        {filteredPosts.length === 0 && (
          <p className="text-sm text-slate-400 text-center py-8">No posts found.</p>
        )}
        {filteredPosts.map((p) => (
          <article
            key={p.post_id}
            className="bg-white border border-slate-200 rounded-2xl p-5 hover:shadow-md hover:border-slate-350 transition-all duration-150 shadow-sm"
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="w-9 h-9 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-100/50 flex items-center justify-center font-bold text-sm shrink-0">
                {p.avatar_initial}
              </div>
              <div>
                <p className="text-sm font-bold text-slate-900">{p.display_name}</p>
                <p className="text-xs text-slate-500 font-semibold mt-0.5">
                  @{p.username} · {timeAgo(p.created_at)}
                </p>
              </div>
            </div>
            {p.content && (
              <p className="text-sm text-slate-700 whitespace-pre-wrap mb-3 leading-relaxed">{p.content}</p>
            )}
            {p.code_snippet && (
              <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden mb-3 shadow-md">
                <div className="flex items-center justify-between px-4 py-1.5 bg-slate-950 border-b border-slate-850/60 text-[10px] text-slate-400 font-mono">
                  <span>{p.language || 'plaintext'}</span>
                  <button
                    onClick={() => navigator.clipboard.writeText(p.code_snippet || '')}
                    className="hover:text-white transition-colors"
                  >
                    Copy Code
                  </button>
                </div>
                <pre className="p-4 text-xs font-mono text-slate-100 overflow-x-auto">
                  <code>{p.code_snippet}</code>
                </pre>
              </div>
            )}
            <div className="flex items-center gap-4 text-slate-500 text-xs mt-3 pt-3 border-t border-slate-100">
              <button
                onClick={() => handleLike(p.post_id)}
                disabled={!isAuthenticated}
                className="flex items-center gap-1.5 hover:text-rose-500 disabled:hover:text-slate-500 transition-colors"
              >
                <Heart className="w-4 h-4 text-slate-400" /> {p.likes_count}
              </button>
              <button
                onClick={() => toggleComments(p.post_id)}
                className="flex items-center gap-1.5 hover:text-indigo-600 transition-colors"
              >
                <MessageCircle className="w-4 h-4 text-slate-400" /> {p.comments_count}
              </button>
            </div>

            {/* Comment Thread drawer */}
            {openComments[p.post_id] && (
              <div className="mt-4 pt-4 border-t border-slate-100 space-y-4">
                <h4 className="text-xs font-bold text-slate-800">Comments</h4>
                {loadingComments[p.post_id] ? (
                  <p className="text-[11px] text-slate-400">Loading comments...</p>
                ) : (
                  <div className="space-y-3">
                    {(postComments[p.post_id] || []).length === 0 && (
                      <p className="text-[11px] text-slate-400">No comments yet. Write one below!</p>
                    )}
                    {(postComments[p.post_id] || []).map((c) => (
                      <div key={c.comment_id} className="flex gap-2.5 items-start text-xs">
                        <div className="w-6 h-6 rounded-full bg-indigo-50 text-indigo-700 flex items-center justify-center font-bold text-[10px] shrink-0">
                          {c.avatar_initial}
                        </div>
                        <div className="flex-1 bg-slate-50 p-2.5 rounded-xl border border-slate-100">
                          <div className="flex justify-between items-center mb-0.5">
                            <span className="font-bold text-slate-800">{c.display_name}</span>
                            <span className="text-[9px] text-slate-400">{timeAgo(c.created_at)}</span>
                          </div>
                          <p className="text-slate-655 text-slate-600 leading-normal">{c.content}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {isAuthenticated && (
                  <div className="flex gap-2">
                    <input
                      value={commentInputs[p.post_id] || ''}
                      onChange={(e) => setCommentInputs({ ...commentInputs, [p.post_id]: e.target.value })}
                      onKeyDown={(e) => e.key === 'Enter' && handleAddComment(p.post_id)}
                      placeholder="Write a comment..."
                      className="flex-1 text-xs border border-slate-200 rounded-xl px-3 py-2.5 focus:outline-none focus:border-indigo-500 bg-white"
                    />
                    <button
                      onClick={() => handleAddComment(p.post_id)}
                      className="text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-700 px-4 py-2.5 rounded-xl"
                    >
                      Reply
                    </button>
                  </div>
                )}
              </div>
            )}
          </article>
        ))}
      </div>
    </div>
  );
};

export default FeedPage;
