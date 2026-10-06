import { useState, type FormEvent } from 'react'
import type { Device, DeviceConfig } from '../lib/api'
import { validateConfig } from '../lib/air'

interface Props {
  device: Device
  onSave: (cfg: DeviceConfig, token: string) => Promise<void>
}

export function ConfigForm({ device, onSave }: Props) {
  const [co2, setCo2] = useState(device.co2_alert_ppm)
  const [temp, setTemp] = useState(device.temp_max_c)
  const [interval, setIntervalS] = useState(device.interval_s)
  const [token, setToken] = useState('')
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const cfg = { co2_alert_ppm: co2, temp_max_c: temp, interval_s: interval }
    const err = validateConfig(cfg)
    if (err) return setMsg({ ok: false, text: err })
    if (!token) return setMsg({ ok: false, text: 'Admin token required' })
    try {
      await onSave(cfg, token)
      setMsg({ ok: true, text: 'Saved. The device applies it on its next shadow update.' })
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : 'Save failed' })
    }
  }

  const input = 'mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm'
  return (
    <form onSubmit={submit} className="grid grid-cols-2 gap-3 sm:grid-cols-4" noValidate>
      <label className="text-xs font-medium text-slate-600">CO₂ alert (ppm)
        <input type="number" className={input} value={co2} onChange={e => setCo2(Number(e.target.value))} />
      </label>
      <label className="text-xs font-medium text-slate-600">Max temp (°C)
        <input type="number" step="0.5" className={input} value={temp} onChange={e => setTemp(Number(e.target.value))} />
      </label>
      <label className="text-xs font-medium text-slate-600">Report every (s)
        <input type="number" className={input} value={interval} onChange={e => setIntervalS(Number(e.target.value))} />
      </label>
      <label className="text-xs font-medium text-slate-600">Admin token
        <input type="password" className={input} value={token} onChange={e => setToken(e.target.value)} autoComplete="off" />
      </label>
      <div className="col-span-2 flex items-center gap-3 sm:col-span-4">
        <button className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700">Save settings</button>
        {msg && <p role="status" className={`text-sm ${msg.ok ? 'text-emerald-700' : 'text-red-600'}`}>{msg.text}</p>}
      </div>
    </form>
  )
}
