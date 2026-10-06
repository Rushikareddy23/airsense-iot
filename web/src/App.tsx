import { useCallback, useState } from 'react'
import { ConfigForm } from './components/ConfigForm'
import { MetricChart } from './components/MetricChart'
import { ago, co2Level, LEVEL_STYLE } from './lib/air'
import { api, type Device, type Point } from './lib/api'
import { usePolling } from './lib/usePolling'

const RANGES = [{ label: '1h', min: 60 }, { label: '6h', min: 360 }, { label: '24h', min: 1440 }, { label: '7d', min: 10080 }]

function Tile({ label, value, unit, extra }: { label: string; value: string; unit: string; extra?: React.ReactNode }) {
  return (
    <div className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}<span className="ml-1 text-sm font-normal text-slate-500">{unit}</span></p>
      {extra}
    </div>
  )
}

export default function App() {
  const [devices, setDevices] = useState<Device[] | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [minutes, setMinutes] = useState(360)
  const [points, setPoints] = useState<Point[]>([])
  const [error, setError] = useState<string | null>(null)

  const current = devices?.find(d => d.device_id === selected) ?? devices?.[0] ?? null

  const load = useCallback(async () => {
    try {
      const ds = await api.devices()
      setDevices(ds)
      const id = selected ?? ds[0]?.device_id
      if (id) setPoints(await api.readings(id, minutes))
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Cannot reach the API')
    }
  }, [selected, minutes])
  usePolling(load, 10000)

  const latest = current?.latest
  const level = latest ? co2Level(latest.co2_ppm) : null
  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">AirSense</h1>
          <p className="text-sm text-slate-500">Indoor air quality · ESP32 + AWS IoT</p>
        </div>
        <div className="flex gap-1 text-sm" role="group" aria-label="Time range">
          {RANGES.map(r => (
            <button key={r.min} onClick={() => setMinutes(r.min)} aria-pressed={r.min === minutes}
              className={`rounded-md px-3 py-1 ${r.min === minutes ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'}`}>{r.label}</button>
          ))}
        </div>
      </header>

      {error && <p role="alert" className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {devices?.length === 0 && <p className="text-slate-500">No devices have reported yet. Start the simulator or power on your ESP32.</p>}

      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        <nav aria-label="Devices" className="space-y-2">
          {devices?.map(d => (
            <button key={d.device_id} onClick={() => setSelected(d.device_id)}
              className={`w-full rounded-lg p-3 text-left ring-1 ${d.device_id === current?.device_id ? 'bg-white ring-slate-400' : 'bg-white/60 ring-slate-200 hover:bg-white'}`}>
              <div className="flex items-center justify-between">
                <span className="font-medium">{d.device_id}</span>
                <span className={`text-xs ${d.online ? 'text-emerald-700' : 'text-slate-500'}`}>{d.online ? '● online' : '○ offline'}</span>
              </div>
              <p className="text-xs text-slate-500">
                {d.latest ? `${d.latest.co2_ppm} ppm · ${d.latest.temp_c.toFixed(1)} °C` : 'no data'} · {ago(d.last_ts)}
              </p>
              {d.alert_state === 'alerting' && <p className="mt-1 text-xs font-medium text-red-700">■ Alert active</p>}
            </button>
          ))}
        </nav>

        {current && latest && level && (
          <main className="space-y-4">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
              <Tile label="CO₂" value={String(latest.co2_ppm)} unit="ppm"
                extra={<span className={`mt-2 inline-block rounded-full px-2 py-0.5 text-xs font-medium ${LEVEL_STYLE[level].cls}`}>
                  {LEVEL_STYLE[level].icon} {LEVEL_STYLE[level].label}</span>} />
              <Tile label="Temperature" value={latest.temp_c.toFixed(1)} unit="°C" />
              <Tile label="Humidity" value={latest.humidity_pct.toFixed(0)} unit="%" />
              <Tile label="Pressure" value={latest.pressure_hpa.toFixed(0)} unit="hPa" />
              <Tile label="TVOC" value={String(latest.tvoc_ppb)} unit="ppb" />
            </div>
            <MetricChart title="CO₂" points={points} dataKey="co2_ppm" unit="ppm" threshold={current.co2_alert_ppm} thresholdLabel="alert level" />
            <div className="grid gap-4 md:grid-cols-2">
              <MetricChart title="Temperature" points={points} dataKey="temp_c" unit="°C" color="#eb6834" threshold={current.temp_max_c} thresholdLabel="max" />
              <MetricChart title="Humidity" points={points} dataKey="humidity_pct" unit="%" color="#1baf7a" />
            </div>
            <details className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
              <summary className="cursor-pointer text-sm font-medium">Device settings</summary>
              <div className="mt-3">
                <ConfigForm key={current.device_id} device={current}
                  onSave={async (cfg, token) => { await api.updateConfig(current.device_id, cfg, token); await load() }} />
              </div>
            </details>
          </main>
        )}
      </div>
    </div>
  )
}
