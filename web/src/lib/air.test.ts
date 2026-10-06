import { describe, expect, it } from 'vitest'
import { ago, co2Level, validateConfig } from './air'

describe('air helpers', () => {
  it('uses the same CO2 bands as the firmware', () => {
    expect(co2Level(450)).toBe('good')
    expect(co2Level(800)).toBe('moderate')
    expect(co2Level(1200)).toBe('poor')
  })
  it('validates config like the API does', () => {
    expect(validateConfig({ co2_alert_ppm: 1200, temp_max_c: 30, interval_s: 10 })).toBeNull()
    expect(validateConfig({ co2_alert_ppm: 100, temp_max_c: 30, interval_s: 10 })).toMatch(/CO₂/)
    expect(validateConfig({ co2_alert_ppm: 1200, temp_max_c: 30, interval_s: 1 })).toMatch(/Interval/)
  })
  it('formats relative time', () => {
    expect(ago(1000, 1030)).toBe('30s ago')
    expect(ago(null)).toBe('never')
  })
})
