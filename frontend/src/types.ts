export type OrbitSummary = {
  inclination_deg: number | null
  perigee_km: number | null
  apogee_km: number | null
  eccentricity: number | null
}

export type DashboardSummary = {
  total_satellites: number
  valid_satellites: number
  invalid_satellites: number
  tracked_satellites: number
  launch_groups: number
  last_updated_at: string | null
}

export type SatellitePreview = {
  id: number | null
  intl_designator: string
  status: string
  epoch_at: string | null
  group_id: number | null
  group_name: string | null
  group_intl_designator: string | null
  launch_time: string | null
  launch_site: string | null
  rocket_name: string | null
  rocket_serial_number: string | null
  manufacturer_name: string | null
  orbit: OrbitSummary
}

export type LaunchPreview = {
  name: string | null
  intl_designator: string
  launch_time: string | null
  launch_site: string | null
  rocket_name: string | null
  rocket_serial_number: string | null
  manufacturer_name: string | null
  satellite_count: number
  orbit: OrbitSummary
}

export type ManufacturerStat = {
  id: number
  name: string
  group_count: number
  satellite_count: number
}

export type RocketStat = {
  id: number
  name: string
  serial_number: string | null
  launch_count: number
  satellite_count: number
}

export type DashboardData = {
  summary: DashboardSummary
  recent_satellites: SatellitePreview[]
  recent_launches: LaunchPreview[]
  manufacturers: ManufacturerStat[]
  rockets: RocketStat[]
}

export type TimePayload = {
  utc_time: string
  source: 'ntp'
  server: string
  offset_seconds: number
  round_trip_seconds: number | null
  synced_at: string
  cached: boolean
}

export type GroupSummary = {
  id: number
  name: string
  intl_designator: string
  launch_time: string | null
  launch_site: string | null
  rocket_id: number | null
  rocket_name: string | null
  rocket_serial_number: string | null
  manufacturer_id: number | null
  manufacturer_name: string | null
  satellite_count: number
  valid_satellite_count: number
  invalid_satellite_count: number
  orbit: OrbitSummary
}

export type GroupDetail = GroupSummary & {
  satellites: SatellitePreview[]
}

export type HistoryPoint = {
  id: number
  epoch_at: string | null
  perigee_km: number | null
  apogee_km: number | null
}

export type GeoPoint = {
  latitude: number
  longitude: number
  altitude_km: number
  timestamp?: string
}

export type MapGroupTrack = {
  id: number
  name: string | null
  intl_designator: string
  representative_intl_designator: string | null
  satellite_count: number
  valid_satellite_count: number
  invalid_satellite_count: number
  orbit: OrbitSummary
  orbit_type: 'leo' | 'sso' | 'geo'
  raw_tle: string
}

export type MapSatellitePoint = {
  id: number | null
  intl_designator: string
  status: string
  group_id: number | null
  group_name: string | null
  group_intl_designator: string | null
  orbit: OrbitSummary
  orbit_type: 'leo' | 'sso' | 'geo'
  raw_tle: string
}

export type MapPayload = {
  generated_at: string
  groups: MapGroupTrack[]
  skipped_groups: number
}

export type MapPointsPayload = {
  generated_at: string
  satellites: MapSatellitePoint[]
  skipped_satellites: number
}
