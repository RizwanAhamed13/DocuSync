import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import NotificationBell from './NotificationBell';
import {
  LayoutDashboard,
  CloudLightning,
  Newspaper,
  CheckSquare,
  Compass,
  Trophy,
  User,
  LogOut,
  GraduationCap,
  Zap,
  Globe,
  ChevronDown,
} from 'lucide-react';

interface NavItem {
  name: string;
  path: string;
  icon: React.ComponentType<{ className?: string; size?: number }>;
  roles?: string[];
  badge?: string;
}

const NAV_ITEMS: NavItem[] = [
  { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
  { name: 'Deploy', path: '/deploy', icon: CloudLightning },
  { name: 'Tunnels', path: '/tunnels', icon: Globe },
  { name: 'Feed', path: '/feed', icon: Newspaper },
  { name: 'DSA Tracker', path: '/dsa', icon: CheckSquare },
  { name: 'Showcase', path: '/showcase', icon: Compass },
  { name: 'Hackathons', path: '/hackathons', icon: Zap },
  { name: 'Leaderboard', path: '/leaderboard', icon: Trophy },
  { name: 'Faculty', path: '/faculty', icon: GraduationCap, roles: ['faculty', 'admin'] },
];

const MOBILE_ITEMS: NavItem[] = [
  { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
  { name: 'Feed', path: '/feed', icon: Newspaper },
  { name: 'DSA', path: '/dsa', icon: CheckSquare },
  { name: 'Profile', path: '/profile', icon: User },
];

export const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const role = user?.role || 'student';
  const visibleNav = NAV_ITEMS.filter((item) => !item.roles || item.roles.includes(role));

  const crumb = location.pathname.substring(1).split('/')[0] || 'home';
  const crumbLabel = crumb.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

  return (
    <div className="flex min-h-screen bg-slate-50">
      {/* Sidebar */}
      <aside className="hidden md:flex flex-col w-60 shrink-0 bg-white border-r border-slate-200/80 fixed inset-y-0 left-0 z-30 shadow-sm">
        {/* Logo */}
        <div className="h-16 flex items-center px-6 border-b border-slate-100">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-indigo-600 flex items-center justify-center text-white font-black text-sm shadow-md shadow-indigo-600/25">
              Q
            </div>
            <span className="font-extrabold text-slate-900 text-lg tracking-tight">Quad</span>
          </Link>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
          {visibleNav.map((item) => {
            const Icon = item.icon;
            const isActive =
              location.pathname === item.path ||
              (item.path !== '/' && location.pathname.startsWith(item.path));
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                  isActive
                    ? 'bg-indigo-550/10 bg-indigo-50 text-indigo-700'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                }`}
              >
                <Icon size={16} className={isActive ? 'text-indigo-600' : 'text-slate-400'} />
                {item.name}
                {item.badge && (
                  <span className="ml-auto text-[10px] font-bold bg-indigo-100 text-indigo-700 rounded-full px-2 py-0.5">
                    {item.badge}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Bottom user */}
        <div className="border-t border-slate-100 p-4">
          {user && (
            <div className="relative">
              <button
                onClick={() => setUserMenuOpen(!userMenuOpen)}
                className="w-full flex items-center gap-3 px-2 py-2 rounded-xl hover:bg-slate-50 transition-colors text-left"
              >
                <div className="w-8 h-8 rounded-xl bg-indigo-100 text-indigo-700 flex items-center justify-center text-sm font-black shrink-0">
                  {user.avatar_initial || user.username[0].toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-bold text-slate-900 truncate leading-tight">
                    {user.display_name || user.username}
                  </p>
                  <p className="text-xs text-slate-400 font-semibold truncate capitalize mt-0.5">{user.role}</p>
                </div>
                <ChevronDown size={14} className="text-slate-400 shrink-0" />
              </button>
              {userMenuOpen && (
                <div className="absolute bottom-full left-0 right-0 mb-2 bg-white border border-slate-200/80 rounded-2xl shadow-xl py-1.5 z-50">
                  <Link
                    to="/profile"
                    onClick={() => setUserMenuOpen(false)}
                    className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                  >
                    <User size={14} className="text-slate-400" /> Profile
                  </Link>
                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center gap-2 px-4 py-2 text-sm font-semibold text-rose-650 text-rose-600 hover:bg-rose-50/50"
                  >
                    <LogOut size={14} /> Sign out
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </aside>

      {/* Main content area */}
      <div className="flex-1 md:pl-60 flex flex-col min-h-screen">
        {/* Top header */}
        <header className="h-16 bg-white border-b border-slate-200/80 flex items-center justify-between px-8 sticky top-0 z-20 shadow-sm">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <span className="text-slate-400">quad</span>
            <span className="text-slate-300">/</span>
            <span className="text-slate-900 font-bold">{crumbLabel}</span>
          </div>
          <div className="flex items-center gap-4">
            {user && <NotificationBell />}
            <div className="flex items-center gap-2 bg-emerald-50 border border-emerald-200 px-3 py-1 rounded-xl">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping" />
              <span className="text-xs text-emerald-700 font-bold uppercase tracking-wider">live</span>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 p-8 pb-24 md:pb-8">{children}</main>
      </div>

      {/* Mobile bottom nav */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 h-16 bg-white border-t border-slate-200/80 flex items-center justify-around z-40 shadow-lg">
        {MOBILE_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive =
            location.pathname === item.path ||
            (item.path !== '/' && location.pathname.startsWith(item.path));
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`flex flex-col items-center justify-center gap-1.5 flex-1 h-full transition-colors ${
                isActive ? 'text-indigo-600' : 'text-slate-400'
              }`}
            >
              <Icon size={18} />
              <span className="text-[10px] font-bold">{item.name}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
};

export default Layout;
