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
  Settings,
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
    <div className="flex min-h-screen bg-[#f8f9fa]">
      {/* Sidebar */}
      <aside className="hidden md:flex flex-col w-56 shrink-0 bg-white border-r border-gray-200 fixed inset-y-0 left-0 z-30">
        {/* Logo */}
        <div className="h-14 flex items-center px-4 border-b border-gray-200">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center text-white font-black text-sm">
              Q
            </div>
            <span className="font-bold text-gray-900 text-[15px] tracking-tight">Quad</span>
          </Link>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
          {visibleNav.map((item) => {
            const Icon = item.icon;
            const isActive =
              location.pathname === item.path ||
              (item.path !== '/' && location.pathname.startsWith(item.path));
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                }`}
              >
                <Icon size={16} className={isActive ? 'text-blue-600' : 'text-gray-400'} />
                {item.name}
                {item.badge && (
                  <span className="ml-auto text-[10px] font-semibold bg-blue-100 text-blue-700 rounded-full px-1.5 py-0.5">
                    {item.badge}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Bottom user */}
        <div className="border-t border-gray-200 p-3">
          {user && (
            <div className="relative">
              <button
                onClick={() => setUserMenuOpen(!userMenuOpen)}
                className="w-full flex items-center gap-2.5 px-2 py-2 rounded-lg hover:bg-gray-100 transition-colors text-left"
              >
                <div className="w-7 h-7 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold shrink-0">
                  {user.avatar_initial || user.username[0].toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-gray-900 truncate leading-tight">
                    {user.display_name || user.username}
                  </p>
                  <p className="text-xs text-gray-500 truncate capitalize">{user.role}</p>
                </div>
                <ChevronDown size={14} className="text-gray-400 shrink-0" />
              </button>
              {userMenuOpen && (
                <div className="absolute bottom-full left-0 right-0 mb-1 bg-white border border-gray-200 rounded-xl shadow-lg py-1 z-50">
                  <Link
                    to="/profile"
                    onClick={() => setUserMenuOpen(false)}
                    className="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                  >
                    <User size={14} className="text-gray-400" /> Profile
                  </Link>
                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50"
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
      <div className="flex-1 md:pl-56 flex flex-col min-h-screen">
        {/* Top header */}
        <header className="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-6 sticky top-0 z-20">
          <div className="flex items-center gap-2 text-sm">
            <span className="text-gray-400 font-medium">quad</span>
            <span className="text-gray-300">/</span>
            <span className="font-semibold text-gray-900">{crumbLabel}</span>
          </div>
          <div className="flex items-center gap-3">
            {user && <NotificationBell />}
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
              <span className="text-xs text-gray-400 font-mono">live</span>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 p-6 pb-20 md:pb-6">{children}</main>
      </div>

      {/* Mobile bottom nav */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 h-16 bg-white border-t border-gray-200 flex items-center justify-around z-40">
        {MOBILE_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive =
            location.pathname === item.path ||
            (item.path !== '/' && location.pathname.startsWith(item.path));
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`flex flex-col items-center justify-center gap-1 flex-1 h-full transition-colors ${
                isActive ? 'text-blue-600' : 'text-gray-400'
              }`}
            >
              <Icon size={20} />
              <span className="text-[10px] font-medium">{item.name}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
};

export default Layout;
