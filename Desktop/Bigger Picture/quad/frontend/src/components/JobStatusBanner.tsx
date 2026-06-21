import React from 'react';

interface JobStatusBannerProps {
  status: 'idle' | 'queued' | 'running' | 'done' | 'failed';
  error?: string | null;
}

export const JobStatusBanner: React.FC<JobStatusBannerProps> = ({ status, error }) => {
  if (status === 'idle') return null;

  const variants = {
    queued:  'bg-gray-50 border-gray-200 text-gray-600',
    running: 'bg-blue-50 border-blue-200 text-blue-700',
    done:    'bg-green-50 border-green-200 text-green-700',
    failed:  'bg-red-50 border-red-200 text-red-700',
  };

  return (
    <div className={`p-3.5 rounded-xl border flex items-center gap-3 text-sm font-medium transition-all ${variants[status]}`}>
      {status === 'queued' && <div className="w-2 h-2 rounded-full bg-gray-400 animate-pulse shrink-0" />}
      {status === 'running' && <div className="w-3.5 h-3.5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin shrink-0" />}
      {status === 'done' && <div className="w-2 h-2 rounded-full bg-green-500 shrink-0" />}
      {status === 'failed' && <div className="w-2 h-2 rounded-full bg-red-500 shrink-0" />}
      {status === 'queued' && 'Job queued…'}
      {status === 'running' && 'AI is thinking…'}
      {status === 'done' && 'Complete'}
      {status === 'failed' && `Failed: ${error || 'Unknown error'}`}
    </div>
  );
};
export default JobStatusBanner;
