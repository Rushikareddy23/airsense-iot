import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const device = {
  device_id: 'room-1', online: true, alert_state: 'alerting', last_ts: Date.now() / 1000 - 5,
  co2_alert_ppm: 1200, temp_max_c: 30, interval_s: 10,
  latest: { ts: 1, temp_c: 23.4, humidity_pct: 41, pressure_hpa: 1012, co2_ppm: 1350, tvoc_ppb: 80 },
}

function mockApi(putStatus = 200) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === 'PUT') return new Response(JSON.stringify(putStatus === 200 ? {} : { error: 'invalid admin token' }), { status: putStatus })
    if (url.endsWith('/devices')) return new Response(JSON.stringify([device]))
    return new Response(JSON.stringify({ points: [{ ts: 1, temp_c: 23, humidity_pct: 40, pressure_hpa: 1012, co2_ppm: 1300, tvoc_ppb: 70 }] }))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => vi.unstubAllGlobals())

describe('dashboard', () => {
  it('shows latest readings, poor air quality and the active alert', async () => {
    mockApi()
    render(<App />)
    expect(await screen.findByText('1350')).toBeInTheDocument()
    expect(screen.getByText(/Poor — ventilate/)).toBeInTheDocument()
    expect(screen.getByText(/Alert active/)).toBeInTheDocument()
  })

  it('sends config with the admin token and shows server errors', async () => {
    const f = mockApi(401)
    render(<App />)
    await screen.findByText('1350')
    await userEvent.click(screen.getByText('Device settings'))
    await userEvent.type(screen.getByLabelText(/admin token/i), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: /save settings/i }))
    expect(await screen.findByRole('status')).toHaveTextContent('invalid admin token')
    const put = f.mock.calls.find(c => c[1]?.method === 'PUT')!
    expect((put[1]!.headers as Record<string, string>)['x-admin-token']).toBe('wrong')
  })

  it('shows a readable error when the API is down', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Failed to fetch')
  })
})
