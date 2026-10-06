import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Point } from '../lib/api'

interface Props {
  title: string
  points: Point[]
  dataKey: keyof Point
  unit: string
  color?: string
  threshold?: number
  thresholdLabel?: string
}

/** One measure per chart (never a dual axis); optional dashed threshold line. */
export function MetricChart({ title, points, dataKey, unit, color = '#2a78d6', threshold, thresholdLabel }: Props) {
  const fmt = (t: number) => new Date(t * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  return (
    <div className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
      <h3 className="mb-2 text-sm font-medium text-slate-700">{title} <span className="font-normal text-slate-500">({unit})</span></h3>
      {points.length === 0 ? <p className="py-12 text-center text-sm text-slate-500">No data in this range</p> : (
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="#e6e5e0" vertical={false} />
              <XAxis dataKey="ts" type="number" domain={['dataMin', 'dataMax']} scale="time" tickFormatter={fmt}
                tick={{ fontSize: 11, fill: '#52514e' }} minTickGap={40} />
              <YAxis tick={{ fontSize: 11, fill: '#52514e' }} width={44} domain={['auto', 'auto']} />
              <Tooltip labelFormatter={t => new Date(Number(t) * 1000).toLocaleString()}
                formatter={v => [`${v} ${unit}`, title]} />
              {threshold !== undefined && (
                <ReferenceLine y={threshold} stroke="#d03b3b" strokeDasharray="4 4"
                  label={{ value: thresholdLabel, position: 'insideTopRight', fontSize: 11, fill: '#52514e' }} />
              )}
              <Line type="monotone" dataKey={dataKey as string} stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
