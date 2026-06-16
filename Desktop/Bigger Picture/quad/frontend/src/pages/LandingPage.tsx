import React from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import { CloudLightning, Shield, Zap, ArrowRight, Globe, CheckSquare, Trophy, Terminal } from 'lucide-react';

const FEATURES = [
  {
    icon: CloudLightning,
    title: 'Auto-Stack Detection',
    desc: 'Upload a ZIP or connect a Git repo. Quad auto-detects Node, Python, Java, or Static HTML and compiles a build recipe in seconds.',
    color: 'text-blue-600',
    bg: 'bg-blue-50',
  },
  {
    icon: Zap,
    title: 'Scale-to-Zero',
    desc: 'Idle containers are reaped automatically. The proxy wakes them instantly on the next request — zero manual intervention.',
    color: 'text-violet-600',
    bg: 'bg-violet-50',
  },
  {
    icon: Shield,
    title: 'Secure Tunnels',
    desc: 'Expose any local port to the internet via frp-powered tunnels. Get a public subdomain with one click.',
    color: 'text-emerald-600',
    bg: 'bg-emerald-50',
  },
  {
    icon: Terminal,
    title: 'AI Deploy Doctor',
    desc: 'Build failed? Paste your logs and let the AI diagnose the root cause and suggest a fix immediately.',
    color: 'text-orange-600',
    bg: 'bg-orange-50',
  },
  {
    icon: CheckSquare,
    title: 'DSA Tracker',
    desc: 'Track your LeetCode / competitive programming progress and compete on department-wide leaderboards.',
    color: 'text-pink-600',
    bg: 'bg-pink-50',
  },
  {
    icon: Trophy,
    title: 'Hackathons & Showcase',
    desc: 'Host and join hackathons, submit projects, vote for the best apps, and build a public developer portfolio.',
    color: 'text-amber-600',
    bg: 'bg-amber-50',
  },
];

export const LandingPage: React.FC = () => {
  const { isAuthenticated } = useAuth();

  return (
    <div className="min-h-screen bg-white text-gray-900 flex flex-col">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/90 backdrop-blur-md border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center text-white font-black text-sm">
              Q
            </div>
            <span className="font-bold text-gray-900 text-[15px] tracking-tight">Quad</span>
          </Link>

          <nav className="hidden md:flex items-center gap-6 text-sm font-medium text-gray-600">
            <Link to="/showcase" className="hover:text-gray-900 transition-colors">Showcase</Link>
            <Link to="/leaderboard" className="hover:text-gray-900 transition-colors">Leaderboard</Link>
            <Link to="/hackathons" className="hover:text-gray-900 transition-colors">Hackathons</Link>
          </nav>

          <div className="flex items-center gap-2">
            {isAuthenticated ? (
              <Link
                to="/dashboard"
                className="inline-flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
              >
                Dashboard <ArrowRight size={14} />
              </Link>
            ) : (
              <>
                <Link
                  to="/auth"
                  className="text-sm font-medium text-gray-700 hover:text-gray-900 px-3 py-2 rounded-lg hover:bg-gray-100 transition-colors"
                >
                  Sign in
                </Link>
                <Link
                  to="/auth"
                  className="text-sm font-semibold bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors"
                >
                  Get started
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Hero */}
      <main className="flex-1">
        <section className="max-w-6xl mx-auto px-6 pt-24 pb-20 text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-50 border border-blue-200 text-blue-700 text-xs font-semibold mb-8">
            <Zap size={12} className="fill-blue-700/20" />
            Self-Hosted App Engine for Students &amp; Teams
          </div>

          <h1 className="text-5xl md:text-6xl font-extrabold tracking-tight text-gray-900 mb-6 leading-[1.1]">
            Deploy, tunnel, and{' '}
            <span className="text-blue-600">collaborate</span>
            <br />on your own cloud.
          </h1>

          <p className="text-gray-500 text-lg max-w-xl mx-auto mb-10 leading-relaxed">
            Quad is the student platform for deploying full-stack apps, exposing local services, tracking DSA progress, and hosting hackathons — all from one dashboard.
          </p>

          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              to={isAuthenticated ? '/dashboard' : '/auth'}
              className="inline-flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-bold px-7 py-3.5 rounded-xl transition-colors text-base"
            >
              Get started free <ArrowRight size={16} />
            </Link>
            <Link
              to="/showcase"
              className="inline-flex items-center justify-center gap-2 bg-white hover:bg-gray-50 border border-gray-300 text-gray-800 font-semibold px-7 py-3.5 rounded-xl transition-colors text-base"
            >
              <Globe size={16} /> View showcase
            </Link>
          </div>

          {/* Social proof strip */}
          <div className="mt-14 flex items-center justify-center gap-6 flex-wrap text-sm text-gray-400 font-medium">
            {['Node.js', 'Python', 'Java', 'Static HTML', 'Docker', 'frp Tunnels'].map((s) => (
              <span key={s} className="inline-flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                {s}
              </span>
            ))}
          </div>
        </section>

        {/* Dashboard preview placeholder */}
        <section className="max-w-5xl mx-auto px-6 mb-24">
          <div className="rounded-2xl border border-gray-200 bg-gray-50 overflow-hidden shadow-sm">
            <div className="h-8 bg-white border-b border-gray-200 flex items-center gap-1.5 px-4">
              <span className="w-3 h-3 rounded-full bg-red-400" />
              <span className="w-3 h-3 rounded-full bg-yellow-400" />
              <span className="w-3 h-3 rounded-full bg-green-400" />
              <span className="ml-4 text-xs text-gray-400 font-mono">quad · dashboard</span>
            </div>
            <div className="p-6 grid grid-cols-1 md:grid-cols-3 gap-4">
              {['my-portfolio', 'api-server', 'ml-demo'].map((name, i) => (
                <div key={name} className="bg-white rounded-xl border border-gray-200 p-4">
                  <div className="flex items-center justify-between mb-3">
                    <span className="font-semibold text-gray-900 text-sm">{name}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${
                      i === 0 ? 'bg-green-50 text-green-700 border border-green-200' :
                      i === 1 ? 'bg-blue-50 text-blue-700 border border-blue-200' :
                      'bg-gray-100 text-gray-500 border border-gray-200'
                    }`}>
                      {i === 0 ? 'RUNNING' : i === 1 ? 'BUILDING' : 'STOPPED'}
                    </span>
                  </div>
                  <div className="text-xs text-gray-500 font-mono">{['static', 'node:18', 'python:3.11'][i]}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Features */}
        <section className="max-w-6xl mx-auto px-6 pb-24">
          <div className="text-center mb-14">
            <h2 className="text-3xl font-bold text-gray-900 mb-3">Everything in one place</h2>
            <p className="text-gray-500 text-base max-w-md mx-auto">
              From deployment to community — Quad is the complete platform for builders.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {FEATURES.map((f) => {
              const Icon = f.icon;
              return (
                <div key={f.title} className="p-6 rounded-2xl bg-white border border-gray-200 hover:border-gray-300 hover:shadow-sm transition-all">
                  <div className={`w-10 h-10 rounded-xl ${f.bg} flex items-center justify-center mb-4`}>
                    <Icon size={20} className={f.color} />
                  </div>
                  <h3 className="font-semibold text-gray-900 mb-2">{f.title}</h3>
                  <p className="text-gray-500 text-sm leading-relaxed">{f.desc}</p>
                </div>
              );
            })}
          </div>
        </section>

        {/* CTA */}
        <section className="border-t border-gray-200 bg-gray-50 py-20">
          <div className="max-w-2xl mx-auto text-center px-6">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">Ready to build?</h2>
            <p className="text-gray-500 mb-8">Create your account and deploy your first app in under 5 minutes.</p>
            <Link
              to={isAuthenticated ? '/dashboard' : '/auth'}
              className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-bold px-8 py-3.5 rounded-xl transition-colors text-base"
            >
              {isAuthenticated ? 'Go to Dashboard' : 'Start for free'} <ArrowRight size={16} />
            </Link>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-200 py-6 text-center text-sm text-gray-400">
        <div className="flex items-center justify-center gap-1.5">
          <div className="w-5 h-5 rounded-md bg-blue-600 flex items-center justify-center text-white font-black text-[10px]">Q</div>
          <span>Quad · Self-Hosted Platform · {new Date().getFullYear()}</span>
        </div>
      </footer>
    </div>
  );
};
export default LandingPage;
