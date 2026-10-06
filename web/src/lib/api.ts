export interface Latest {
  ts: number
  temp_c: number
  humidity_pct: number
  pressure_hpa: number
  co2_ppm: number
  tvoc_ppb: number
}

export interface Device {
  device_id: string
  latest: Latest | null
  last_ts: number | null
  online: boolean
  alert_state: 'ok' | 'alerting'
  co2_alert_ppm: number
  temp_max_c: number
  interval_s: number
}

export interface Point extends Latest {
  co2_ppm_max?: number
}

export interface DeviceConfig {
  co2_alert_ppm?: number
  temp_max_c?: number
  interval_s?: number
}

const BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8001').replace(/\/$/, '')

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(body.error ?? `Request failed (${res.status})`)
  return body as T
}

export const api = {
  devices: () => request<Device[]>('/devices'),
  readings: (id: string, minutes: number) =>
    request<{ points: Point[] }>(`/devices/${encodeURIComponent(id)}/readings?minutes=${minutes}`).then(r => r.points),
  updateConfig: (id: string, cfg: DeviceConfig, adminToken: string) =>
    request(`/devices/${encodeURIComponent(id)}/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'x-admin-token': adminToken },
      body: JSON.stringify(cfg),
    }),
}
