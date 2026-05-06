const rawBase = import.meta.env.VITE_API_BASE ?? "";
const base = rawBase.endsWith("/") ? rawBase.slice(0, -1) : rawBase;

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const url = base ? `${base}${path}` : path;
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`${res.status}: ${err}`);
  }
  return res.json() as Promise<T>;
}

export type IncidentSummary = {
  id: string;
  component_id: string;
  component_type: string;
  severity: string;
  alert_tier: string;
  status: string;
  signal_count: number;
  first_signal_at: string;
  updated_at: string | null;
};

export type RawSignal = {
  id: string;
  work_item_id: string;
  component_id: string;
  message: string;
  payload: Record<string, unknown>;
  received_at: string;
};

export type Rca = {
  incident_start: string;
  incident_end: string;
  root_cause_category: string;
  fix_applied: string;
  prevention_steps: string;
  mttr_seconds: number | null;
};

export type WorkItemDetail = IncidentSummary & {
  rca: Rca | null;
  signals: RawSignal[];
};

export const api = {
  health: () => fetchJson<{ status: string; checks: Record<string, boolean> }>("/health"),
  incidentsSorted: () => fetchJson<IncidentSummary[]>("/incidents/sorted"),
  incident: (id: string) => fetchJson<WorkItemDetail>(`/incidents/${id}`),
  patchStatus: (id: string, status: string) =>
    fetchJson<{ ok: boolean }>(`/incidents/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  upsertRca: (id: string, body: Record<string, string>) =>
    fetchJson<{ ok: boolean }>(`/incidents/${id}/rca`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
};
