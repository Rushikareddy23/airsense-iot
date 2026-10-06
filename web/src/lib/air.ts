export type Level = 'good' | 'moderate' | 'poor'

// Same bands as the firmware (lib/core/reading.h) so device LED and dashboard agree.
export function co2Level(ppm: number, moderate = 800, poor = 1200): Level {
  if (ppm >= poor) return 'poor'
  if (ppm >= moderate) return 'moderate'
  return 'good'
}

export const LEVEL_STYLE: Record<Level, { label: string; cls: string; icon: string }> = {
  good: { label: 'Good', cls: 'bg-emerald-50 text-emerald-700', icon: '●' },
  moderate: { label: 'Moderate', cls: 'bg-amber-50 text-amber-800', icon: '▲' },
  poor: { label: 'Poor — ventilate', cls: 'bg-red-50 text-red-700', icon: '■' },
}

export function ago(ts: number | null, now = Date.now() / 1000): string {
  if (!ts) return 'never'
  const s = Math.max(0, Math.round(now - ts))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  return `${Math.floor(s / 3600)}h ago`
}

export function validateConfig(cfg: { co2_alert_ppm: number; temp_max_c: number; interval_s: number }): string | null {
  if (!(cfg.co2_alert_ppm >= 600 && cfg.co2_alert_ppm <= 5000)) return 'CO₂ alert must be 600–5000 ppm'
  if (!(cfg.temp_max_c >= 15 && cfg.temp_max_c <= 60)) return 'Max temperature must be 15–60 °C'
  if (!(cfg.interval_s >= 5 && cfg.interval_s <= 3600)) return 'Interval must be 5–3600 s'
  return null
}
