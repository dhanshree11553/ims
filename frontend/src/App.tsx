import { useCallback, useEffect, useState } from "react";
import { api, IncidentSummary, WorkItemDetail } from "./api";

const RCA_CATEGORIES = [
  "Configuration",
  "Capacity / Load",
  "Dependency failure",
  "Code defect",
  "Data corruption",
  "Network",
  "Security incident",
  "Unknown / Other",
];

function severityColor(sev: string): string {
  switch (sev.toLowerCase()) {
    case "critical":
      return "var(--critical)";
    case "high":
      return "var(--high)";
    case "medium":
      return "var(--medium)";
    case "low":
      return "var(--low)";
    default:
      return "var(--muted)";
  }
}

export default function App() {
  const [health, setHealth] = useState<string>("…");
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<WorkItemDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const loadFeed = useCallback(async () => {
    try {
      const list = await api.incidentsSorted();
      setIncidents(list);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load incidents");
    }
  }, []);

  useEffect(() => {
    api.health().then((h) => setHealth(h.status)).catch(() => setHealth("unreachable"));
  }, []);

  useEffect(() => {
    loadFeed();
    const t = setInterval(loadFeed, 4000);
    return () => clearInterval(t);
  }, [loadFeed]);

  const reloadDetail = useCallback(async () => {
    if (!selected) return;
    try {
      const d = await api.incident(selected);
      setDetail(d);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Detail load failed");
    }
  }, [selected]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    api
      .incident(selected)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((e) => setErr(e instanceof Error ? e.message : "Detail load failed"));
    return () => {
      cancelled = true;
    };
  }, [selected]);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "340px 1fr", minHeight: "100vh" }}>
      <aside
        style={{
          borderRight: "1px solid var(--border)",
          background: "var(--surface)",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <header style={{ padding: "1.25rem", borderBottom: "1px solid var(--border)" }}>
          <h1 style={{ margin: 0, fontSize: "1.15rem", fontWeight: 700 }}>IMS Dashboard</h1>
          <p style={{ margin: "0.35rem 0 0", color: "var(--muted)", fontSize: "0.85rem" }}>
            API: <span className="mono">{health}</span>
          </p>
        </header>
        <div style={{ padding: "0.75rem", overflow: "auto", flex: 1 }}>
          <p style={{ margin: "0 0 0.5rem", fontSize: "0.75rem", color: "var(--muted)", textTransform: "uppercase" }}>
            Live feed · by severity
          </p>
          {err && (
            <p style={{ color: "var(--critical)", fontSize: "0.85rem" }} role="alert">
              {err}
            </p>
          )}
          {incidents.length === 0 && !err && (
            <p style={{ color: "var(--muted)", fontSize: "0.9rem" }}>No active incidents. Ingest signals to begin.</p>
          )}
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {incidents.map((i) => (
              <li key={i.id}>
                <button
                  type="button"
                  onClick={() => setSelected(i.id)}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    padding: "0.75rem",
                    marginBottom: "0.35rem",
                    borderRadius: "var(--radius)",
                    border: selected === i.id ? "1px solid var(--accent)" : "1px solid var(--border)",
                    background: selected === i.id ? "rgba(61,156,245,0.12)" : "var(--bg)",
                    color: "var(--text)",
                    cursor: "pointer",
                  }}
                >
                  <span
                    style={{
                      display: "inline-block",
                      width: 8,
                      height: 8,
                      borderRadius: 999,
                      background: severityColor(i.severity),
                      marginRight: 8,
                      verticalAlign: "middle",
                    }}
                  />
                  <span className="mono" style={{ fontSize: "0.8rem" }}>
                    {i.alert_tier}
                  </span>{" "}
                  <strong>{i.component_id}</strong>
                  <div style={{ fontSize: "0.8rem", color: "var(--muted)", marginTop: 4 }}>
                    {i.status} · {i.signal_count} signals · {i.severity}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </aside>
      <main style={{ padding: "1.5rem", overflow: "auto" }}>
        {!selected && (
          <p style={{ color: "var(--muted)" }}>Select an incident to view raw signals and RCA workflow.</p>
        )}
        {detail && <IncidentPanel detail={detail} onRefresh={reloadDetail} />}
      </main>
    </div>
  );
}

function IncidentPanel({ detail, onRefresh }: { detail: WorkItemDetail; onRefresh: () => Promise<void> }) {
  const [status, setStatus] = useState(detail.status);
  const [rcaStart, setRcaStart] = useState(detail.rca?.incident_start?.slice(0, 16) ?? "");
  const [rcaEnd, setRcaEnd] = useState(detail.rca?.incident_end?.slice(0, 16) ?? "");
  const [category, setCategory] = useState(detail.rca?.root_cause_category ?? "");
  const [fix, setFix] = useState(detail.rca?.fix_applied ?? "");
  const [prevent, setPrevent] = useState(detail.rca?.prevention_steps ?? "");
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    setStatus(detail.status);
    setRcaStart(detail.rca?.incident_start?.slice(0, 16) ?? "");
    setRcaEnd(detail.rca?.incident_end?.slice(0, 16) ?? "");
    setCategory(detail.rca?.root_cause_category ?? "");
    setFix(detail.rca?.fix_applied ?? "");
    setPrevent(detail.rca?.prevention_steps ?? "");
  }, [detail]);

  async function saveRca() {
    setMsg(null);
    try {
      await api.upsertRca(detail.id, {
        incident_start: new Date(rcaStart).toISOString(),
        incident_end: new Date(rcaEnd).toISOString(),
        root_cause_category: category,
        fix_applied: fix,
        prevention_steps: prevent,
      });
      setMsg("RCA saved.");
      await onRefresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "RCA save failed");
    }
  }

  async function advance(next: string) {
    setMsg(null);
    try {
      await api.patchStatus(detail.id, next);
      setStatus(next);
      setMsg(`Status → ${next}`);
      await onRefresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Status update failed");
    }
  }

  return (
    <div>
      <header style={{ marginBottom: "1.5rem" }}>
        <h2 style={{ margin: "0 0 0.25rem" }}>{detail.component_id}</h2>
        <p style={{ margin: 0, color: "var(--muted)" }}>
          {detail.component_type} · {detail.alert_tier} · <span className="mono">{detail.id}</span>
        </p>
      </header>

      <section
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          padding: "1rem",
          marginBottom: "1rem",
        }}
      >
        <h3 style={{ marginTop: 0 }}>Workflow</h3>
        <p>
          Current: <strong>{status}</strong>
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {status === "OPEN" && (
            <button type="button" onClick={() => advance("INVESTIGATING")}>
              Start investigating
            </button>
          )}
          {status === "INVESTIGATING" && (
            <>
              <button type="button" onClick={() => advance("RESOLVED")}>
                Mark resolved
              </button>
              <button type="button" onClick={() => advance("OPEN")}>
                Back to open
              </button>
            </>
          )}
          {status === "RESOLVED" && (
            <>
              <button type="button" onClick={() => advance("CLOSED")}>
                Close (requires complete RCA)
              </button>
              <button type="button" onClick={() => advance("INVESTIGATING")}>
                Re-open investigation
              </button>
            </>
          )}
        </div>
        {detail.rca?.mttr_seconds != null && (
          <p style={{ marginTop: "0.75rem", color: "var(--muted)" }}>
            MTTR: <span className="mono">{(detail.rca.mttr_seconds / 60).toFixed(2)}</span> minutes
          </p>
        )}
      </section>

      <section
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          padding: "1rem",
          marginBottom: "1rem",
        }}
      >
        <h3 style={{ marginTop: 0 }}>Raw signals (NoSQL audit)</h3>
        <div style={{ maxHeight: 280, overflow: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--muted)" }}>
                <th style={{ padding: "0.35rem" }}>Received</th>
                <th style={{ padding: "0.35rem" }}>Message</th>
              </tr>
            </thead>
            <tbody>
              {detail.signals.map((s) => (
                <tr key={s.id} style={{ borderTop: "1px solid var(--border)" }}>
                  <td className="mono" style={{ padding: "0.35rem", whiteSpace: "nowrap" }}>
                    {new Date(s.received_at).toLocaleString()}
                  </td>
                  <td style={{ padding: "0.35rem" }}>
                    {s.message || "—"}
                    <pre
                      style={{
                        margin: "0.25rem 0 0",
                        fontSize: "0.75rem",
                        color: "var(--muted)",
                        whiteSpace: "pre-wrap",
                      }}
                    >
                      {JSON.stringify(s.payload, null, 0)}
                    </pre>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          padding: "1rem",
        }}
      >
        <h3 style={{ marginTop: 0 }}>Root Cause Analysis</h3>
        <div style={{ display: "grid", gap: "0.75rem", maxWidth: 560 }}>
          <label>
            Incident start
            <input
              type="datetime-local"
              value={rcaStart}
              onChange={(e) => setRcaStart(e.target.value)}
              style={{ display: "block", width: "100%", marginTop: 4, padding: 8 }}
            />
          </label>
          <label>
            Incident end
            <input
              type="datetime-local"
              value={rcaEnd}
              onChange={(e) => setRcaEnd(e.target.value)}
              style={{ display: "block", width: "100%", marginTop: 4, padding: 8 }}
            />
          </label>
          <label>
            Root cause category
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              style={{ display: "block", width: "100%", marginTop: 4, padding: 8 }}
            >
              <option value="">Select…</option>
              {RCA_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <label>
            Fix applied
            <textarea
              value={fix}
              onChange={(e) => setFix(e.target.value)}
              rows={4}
              style={{ display: "block", width: "100%", marginTop: 4, padding: 8 }}
            />
          </label>
          <label>
            Prevention steps
            <textarea
              value={prevent}
              onChange={(e) => setPrevent(e.target.value)}
              rows={4}
              style={{ display: "block", width: "100%", marginTop: 4, padding: 8 }}
            />
          </label>
          <button type="button" onClick={saveRca}>
            Save RCA
          </button>
        </div>
        {msg && (
          <p style={{ marginTop: "1rem", fontSize: "0.9rem" }} role="status">
            {msg}
          </p>
        )}
      </section>
    </div>
  );
}
