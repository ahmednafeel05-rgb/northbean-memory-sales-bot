"use client";

import { useEffect, useState } from "react";
import { getOpsMetrics } from "../../lib/api";

// Design brief §3.3: counts and metrics only, no customer memory content.
export default function OpsDashboard() {
  const [metrics, setMetrics] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getOpsMetrics()
      .then(setMetrics)
      .catch(() => setError("Could not load metrics."));
  }, []);

  return (
    <>
      <header className="topbar">
        <h1>Northbean Coffee — Ops dashboard</h1>
        <nav>
          <a href="/">Back to shop</a>
        </nav>
      </header>
      <main className="layout">
        <div className="panel" style={{ flex: 1 }}>
          {error && <p>{error}</p>}
          {!metrics && !error && <p>Loading…</p>}
          {metrics && (
            <table className="metrics">
              <tbody>
                <tr>
                  <th>Memory writes</th>
                  <td>{metrics.writes}</td>
                </tr>
                <tr>
                  <th>Retrievals logged</th>
                  <td>{metrics.retrievals}</td>
                </tr>
                <tr>
                  <th>Fallback rate (memory skipped)</th>
                  <td>{metrics.fallback_rate != null ? `${(metrics.fallback_rate * 100).toFixed(1)}%` : "—"}</td>
                </tr>
                <tr>
                  <th>p95 retrieval latency</th>
                  <td>
                    {metrics.p95_retrieval_latency_ms != null
                      ? `${Math.round(metrics.p95_retrieval_latency_ms)} ms`
                      : "—"}
                  </td>
                </tr>
                <tr>
                  <th>Corrections ("that's wrong")</th>
                  <td>{metrics.corrections}</td>
                </tr>
                <tr>
                  <th>Drops by reason</th>
                  <td>
                    {metrics.drops_by_reason.length === 0
                      ? "none"
                      : metrics.drops_by_reason.map((d) => `${d.reason}: ${d.n}`).join(", ")}
                  </td>
                </tr>
                <tr>
                  <th>Blocks by PII type</th>
                  <td>
                    {metrics.blocks_by_entity_type.length === 0
                      ? "none"
                      : metrics.blocks_by_entity_type.map((b) => `${b.entity_type}: ${b.n}`).join(", ")}
                  </td>
                </tr>
                <tr>
                  <th>Last eval results</th>
                  <td>{metrics.last_eval ?? "not run yet"}</td>
                </tr>
              </tbody>
            </table>
          )}
        </div>
      </main>
    </>
  );
}
