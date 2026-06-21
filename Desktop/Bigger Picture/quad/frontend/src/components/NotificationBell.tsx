import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Bell } from 'lucide-react';
import api from '../lib/api';

interface Notification {
  notification_id: string;
  type: string;
  title: string;
  body: string;
  link?: string | null;
  read: number;
  created_at: string;
}

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const diff = Math.max(0, Date.now() - then);
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export const NotificationBell: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [count, setCount] = useState(0);
  const [items, setItems] = useState<Notification[]>([]);
  const panelRef = useRef<HTMLDivElement>(null);

  const fetchCount = useCallback(async () => {
    try {
      const resp = await api.get<{ count: number }>('/notifications/unread-count');
      setCount(resp.data.count);
    } catch {
      /* ignore */
    }
  }, []);

  const fetchItems = useCallback(async () => {
    try {
      const resp = await api.get<Notification[]>('/notifications');
      setItems(resp.data);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    fetchCount();
    // Fallback polling every 60s
    const id = window.setInterval(fetchCount, 60000);
    return () => window.clearInterval(id);
  }, [fetchCount]);

  useEffect(() => {
    if (open) fetchItems();
  }, [open, fetchItems]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  // WebSocket for push notifications
  useEffect(() => {
    const token = localStorage.getItem('quad_token');
    if (!token) return;

    const apiBase = (import.meta.env.VITE_API_URL as string) || window.location.origin;
    const wsBase = apiBase.replace(/^http/, 'ws');
    let ws: WebSocket;

    try {
      ws = new WebSocket(`${wsBase}/notifications/ws?token=${encodeURIComponent(token)}`);

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'notification' && msg.data) {
            setCount((c) => c + 1);
            setItems((prev) => [msg.data, ...prev]);
          }
        } catch (err) {
          console.error('WebSocket notifications parse error:', err);
        }
      };
    } catch (e) {
      console.error('WebSocket notifications connection error:', e);
    }

    return () => {
      if (ws) ws.close();
    };
  }, []);

  const markAllRead = async () => {
    try {
      await api.post('/notifications/read-all');
      setItems((prev) => prev.map((n) => ({ ...n, read: 1 })));
      setCount(0);
    } catch {
      /* ignore */
    }
  };

  const markOneRead = async (id: string) => {
    try {
      await api.post(`/notifications/${id}/read`);
      setItems((prev) => prev.map((n) => (n.notification_id === id ? { ...n, read: 1 } : n)));
      setCount((c) => Math.max(0, c - 1));
    } catch {
      /* ignore */
    }
  };

  const clearAll = async () => {
    try {
      await api.delete('/notifications/clear-all');
      setItems([]);
      setCount(0);
    } catch {
      /* ignore */
    }
  };

  const clearOne = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    e.preventDefault();
    try {
      await api.delete(`/notifications/${id}`);
      const item = items.find((n) => n.notification_id === id);
      if (item && !item.read) {
        setCount((c) => Math.max(0, c - 1));
      }
      setItems((prev) => prev.filter((n) => n.notification_id !== id));
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="relative" ref={panelRef}>
      <button
        onClick={() => setOpen((o) => !o)}
        title="Notifications"
        className="relative w-8 h-8 flex items-center justify-center rounded-md text-gray-500 hover:text-blue-600 hover:bg-gray-50"
      >
        <Bell className="w-4 h-4" />
        {count > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
            {count > 9 ? '9+' : count}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 max-h-96 overflow-auto bg-white border border-gray-200 rounded-xl shadow-lg z-50">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-gray-50/50">
            <span className="text-xs font-bold text-gray-800">Notifications</span>
            <div className="flex gap-2 items-center">
              <button onClick={markAllRead} className="text-[10px] font-bold text-indigo-650 text-indigo-600 hover:underline">
                Mark all read
              </button>
              <span className="text-gray-300 text-xs">|</span>
              <button onClick={clearAll} className="text-[10px] font-bold text-red-500 hover:underline">
                Clear all
              </button>
            </div>
          </div>
          {items.length === 0 ? (
            <div className="px-4 py-8 text-center text-xs text-gray-400 font-semibold">No notifications</div>
          ) : (
            <div className="divide-y divide-gray-100">
              {items.map((n) => {
                const inner = (
                  <div
                    className={`px-4 py-3 hover:bg-gray-50 transition-colors ${
                      n.read ? 'opacity-60' : ''
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-xs font-bold text-gray-800 leading-tight">{n.title}</span>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <span className="text-[9px] text-gray-400 font-semibold">{timeAgo(n.created_at)}</span>
                        <button
                          onClick={(e) => clearOne(e, n.notification_id)}
                          className="text-gray-400 hover:text-red-500 hover:bg-gray-100 rounded-md p-1 transition-colors flex items-center justify-center"
                          title="Dismiss"
                        >
                          <span className="text-xs font-bold font-mono leading-none">×</span>
                        </button>
                      </div>
                    </div>
                    <p className="text-xs text-gray-500 mt-1 leading-normal">{n.body}</p>
                  </div>
                );
                return n.link ? (
                  <Link
                    key={n.notification_id}
                    to={n.link}
                    onClick={() => {
                      markOneRead(n.notification_id);
                      setOpen(false);
                    }}
                    className="block"
                  >
                    {inner}
                  </Link>
                ) : (
                  <button
                    key={n.notification_id}
                    onClick={() => markOneRead(n.notification_id)}
                    className="block w-full text-left"
                  >
                    {inner}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default NotificationBell;
