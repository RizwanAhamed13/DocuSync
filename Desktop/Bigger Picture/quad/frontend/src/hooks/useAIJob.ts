import { useState } from 'react';
import api from '../lib/api';

export function useAIJob() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "queued" | "running" | "done" | "failed">("idle");
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async (endpoint: string, body: object) => {
    setStatus("queued");
    setResult(null);
    setError(null);
    try {
      const res = await api.post(endpoint, body);
      const id = res.data.job_id;
      setJobId(id);
      
      // poll every 2s until DONE or FAILED
      const interval = setInterval(async () => {
        try {
          const job = await api.get(`/ai/jobs/${id}`);
          const s = job.data.status.toLowerCase() as "queued" | "running" | "done" | "failed";
          setStatus(s);
          if (s === "done") {
            setResult(job.data.result);
            clearInterval(interval);
          } else if (s === "failed") {
            setError(job.data.error || "Job failed");
            clearInterval(interval);
          }
        } catch (err: any) {
          setError(err.response?.data?.detail || "Error polling job status");
          setStatus("failed");
          clearInterval(interval);
        }
      }, 2000);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Error submitting job");
      setStatus("failed");
    }
  };

  return { submit, status, result, error, jobId };
}
