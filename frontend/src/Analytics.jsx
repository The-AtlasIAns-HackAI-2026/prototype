import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { fetchAnalytics } from "./api.js";

export default function Analytics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      setData(await fetchAnalytics());
    } catch {
      setError("Analytics API unavailable.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 15000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <section className="analytics" dir="ltr">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Live</p>
          <h1>Analytics</h1>
        </div>
        <button type="button" className="icon-button" onClick={load} title="Refresh">
          <RefreshCw size={18} />
        </button>
      </div>

      {loading && !data && <p className="muted">Loading...</p>}
      {error && <p className="error">{error}</p>}

      {data && (
        <>
          <div className="metric-grid">
            <Metric label="Events" value={data.total_events} />
            <Metric label="Success" value={`${Math.round(data.success_rate * 100)}%`} />
            <Metric label="Avg words" value={data.average_words} />
            <Metric label="Words" value={data.total_words} />
          </div>

          <div className="analytics-table">
            <div className="table-row table-head">
              <span>Time</span>
              <span>Topic</span>
              <span>Lang</span>
              <span>Status</span>
            </div>
            {data.recent.map((event, index) => (
              <div className="table-row" key={`${event.timestamp}-${index}`}>
                <span>{new Date(event.timestamp).toLocaleTimeString()}</span>
                <span>{event.topic}</span>
                <span>{event.language}</span>
                <span>{event.success ? "ok" : "fail"}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
