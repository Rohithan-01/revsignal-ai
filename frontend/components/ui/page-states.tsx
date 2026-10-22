import { AlertCircle, LoaderCircle, RefreshCw } from "lucide-react";

export function LoadingState({ label = "Loading revenue data" }: { label?: string }) {
  return <div className="loading-state"><LoaderCircle className="spin" size={21} /><span>{label}…</span></div>;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="error-state" role="alert">
      <AlertCircle size={20} />
      <div><strong>We couldn’t load this view</strong><span>{message}</span></div>
      <button className="button button-secondary button-small" onClick={onRetry}><RefreshCw size={14} /> Try again</button>
    </div>
  );
}
