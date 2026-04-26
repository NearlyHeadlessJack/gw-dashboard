import {
  degreesLat,
  degreesLong,
  eciToGeodetic,
  gstime,
  propagate,
  twoline2satrec,
  type EciVec3,
  type SatRec,
} from 'satellite.js'
import type { GeoPoint } from './types'

const TWO_PI = Math.PI * 2
const DEFAULT_TRACK_POINT_COUNT = 600

const satrecCache = new Map<string, SatRec | null>()

export function propagateTlePosition(rawTle: string, at: Date): GeoPoint | null {
  const satrec = satrecFromRawTle(rawTle)
  if (!satrec) return null

  try {
    const result = propagate(satrec, at)
    if (!hasEciPosition(result.position)) return null

    const geodetic = eciToGeodetic(result.position, gstime(at))
    return {
      latitude: degreesLat(geodetic.latitude),
      longitude: normalizeLongitude(degreesLong(geodetic.longitude)),
      altitude_km: geodetic.height,
      timestamp: at.toISOString(),
    }
  } catch {
    return null
  }
}

export function generatePreviousOrbitTrack(
  rawTle: string,
  at: Date,
  pointCount = DEFAULT_TRACK_POINT_COUNT,
): GeoPoint[] {
  const periodMinutes = orbitalPeriodMinutes(rawTle)
  if (!periodMinutes) return []

  const periodMs = periodMinutes * 60_000
  const startMs = at.getTime() - periodMs
  const stepMs = periodMs / pointCount
  const points: GeoPoint[] = []

  for (let index = 0; index <= pointCount; index += 1) {
    const point = propagateTlePosition(rawTle, new Date(startMs + stepMs * index))
    if (point) points.push(point)
  }

  return points
}

function orbitalPeriodMinutes(rawTle: string): number | null {
  const satrec = satrecFromRawTle(rawTle)
  if (!satrec || satrec.no <= 0) return null
  return TWO_PI / satrec.no
}

function satrecFromRawTle(rawTle: string): SatRec | null {
  if (satrecCache.has(rawTle)) {
    return satrecCache.get(rawTle) ?? null
  }

  const lines = tleLines(rawTle)
  if (!lines) {
    satrecCache.set(rawTle, null)
    return null
  }

  try {
    const satrec = twoline2satrec(lines.line1, lines.line2)
    satrecCache.set(rawTle, satrec)
    return satrec
  } catch {
    satrecCache.set(rawTle, null)
    return null
  }
}

function tleLines(rawTle: string): { line1: string; line2: string } | null {
  const lines = rawTle
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
  const line1 = lines.find((line) => line.startsWith('1 '))
  const line2 = lines.find((line) => line.startsWith('2 '))
  return line1 && line2 ? { line1, line2 } : null
}

function hasEciPosition(value: unknown): value is EciVec3<number> {
  if (!value || typeof value !== 'object') return false
  const position = value as Partial<EciVec3<number>>
  return (
    typeof position.x === 'number' &&
    typeof position.y === 'number' &&
    typeof position.z === 'number'
  )
}

function normalizeLongitude(value: number): number {
  return ((((value + 180) % 360) + 360) % 360) - 180
}
