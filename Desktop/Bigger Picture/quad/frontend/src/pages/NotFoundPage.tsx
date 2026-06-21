import React from 'react';
import { Link } from 'react-router-dom';
import { Home, Compass } from 'lucide-react';

export const NotFoundPage: React.FC = () => {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 px-6 py-12">
      <div className="max-w-md w-full text-center space-y-8 p-10 bg-white border border-slate-200 rounded-3xl shadow-xl backdrop-blur-md bg-opacity-70">
        <div className="relative flex justify-center">
          <div className="absolute -top-4 w-28 h-28 bg-indigo-100 rounded-full blur-xl opacity-70 animate-pulse" />
          <Compass className="w-16 h-16 text-indigo-600 relative z-10 animate-bounce" />
        </div>
        
        <div className="space-y-3">
          <h1 className="text-8xl font-black bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">
            404
          </h1>
          <h2 className="text-2xl font-extrabold text-slate-800">
            Lost in Space
          </h2>
          <p className="text-slate-550 text-sm font-semibold max-w-xs mx-auto">
            The page you're looking for doesn't exist, has been moved, or is under construction.
          </p>
        </div>

        <div className="pt-4">
          <Link
            to="/dashboard"
            className="inline-flex items-center gap-2 text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-2xl px-6 py-3.5 transition-all shadow-lg shadow-indigo-600/20 hover:shadow-indigo-600/35 hover:-translate-y-0.5"
          >
            <Home className="w-4 h-4" /> Back to Dashboard
          </Link>
        </div>
      </div>
    </div>
  );
};

export default NotFoundPage;
