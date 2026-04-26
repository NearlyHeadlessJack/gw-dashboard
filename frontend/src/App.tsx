import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent,
} from 'react'
import {
  BrowserRouter,
  Link,
  Navigate,
  NavLink,
  Route,
  Routes,
  useSearchParams,
} from 'react-router-dom'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import {
  Activity,
  AlertCircle,
  ChartLine,
  CircleDot,
  Clock,
  Crosshair,
  Download,
  Factory,
  History,
  LayoutDashboard,
  ListTree,
  Map,
  Orbit,
  RadioTower,
  RefreshCw,
  Rocket,
  Satellite,
  Search,
  Waypoints,
  X,
} from 'lucide-react'
import { useApi } from './api'
import { generatePreviousOrbitTrack, propagateTlePosition } from './orbit'
import type {
  DashboardData,
  GeoPoint,
  GroupDetail,
  GroupSummary,
  HistoryPoint,
  LaunchPreview,
  MapSatellitePoint,
  MapPointsPayload,
  OrbitSummary,
  RocketStat,
  SatellitePreview,
} from './types'
import './App.css'

type IconComponent = typeof LayoutDashboard

type MenuItem = {
  path: string
  label: string
  icon: IconComponent
}

const GAODE_STANDARD_TILE_URL =
  'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={z}'
const LEO_TRACK_COLORS = [
  '#ff6b6b',
  '#4ecdc4',
  '#ffe66d',
  '#a37eba',
  '#f78c6b',
  '#82e0aa',
  '#85c1e9',
  '#f0b27a',
  '#d2b4de',
  '#73c6b6',
]
const OVERVIEW_MAP_HIGH_ORBIT_COLOR = '#ef4444'
const OVERVIEW_MAP_DEFAULT_COLOR = '#2563eb'
const HIGH_ORBIT_ALTITUDE_KM = 35_000
const EXPORT_MAP_WIDTH = 1600
const EXPORT_MAP_HEIGHT = 900
const EXPORT_MAP_ZOOM = 2
const EXPORT_MERCATOR_MAX_LAT = 85.05112878

const DASHBOARD_MENU: MenuItem[] = [
  { path: '/dashboard', label: '总览', icon: LayoutDashboard },
  { path: '/dashboard/orbits', label: '组与单星', icon: Orbit },
  { path: '/dashboard/launches', label: '发射统计', icon: Rocket },
  { path: '/dashboard/history', label: '历史轨道', icon: History },
]

function useClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return now
}

function DashboardLayout() {
  return (
    <div className="dashboard-layout">
      <aside className="sidebar">
        <nav className="sidebar-nav" aria-label="Dashboard sections">
          {DASHBOARD_MENU.map((item) => {
            const Icon = item.icon
            return (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === '/dashboard'}
                className={({ isActive }) =>
                  `menu-item${isActive ? ' active' : ''}`
                }
              >
                <Icon size={17} strokeWidth={1.9} />
                <span className="menu-label">{item.label}</span>
                <span className="menu-indicator" />
              </NavLink>
            )
          })}
        </nav>
        <div className="sidebar-footer">
          <span className="status-dot" />
          <span className="status-text">ONLINE</span>
        </div>
      </aside>
      <main className="dashboard-content">
        <Routes>
          <Route index element={<OverviewPage />} />
          <Route path="orbits" element={<OrbitExplorerPage />} />
          <Route path="launches" element={<LaunchStatsPage />} />
          <Route path="history" element={<HistoryPage />} />
        </Routes>
      </main>
    </div>
  )
}

function OverviewPage() {
  const now = useClock()
  const [mapExporting, setMapExporting] = useState(false)
  const [mapExportError, setMapExportError] = useState<string | null>(null)
  const { data, loading, error } = useApi<DashboardData>('/api/dashboard')
  const {
    data: satellites,
    loading: satellitesLoading,
    error: satellitesError,
  } = useApi<SatellitePreview[]>('/api/satellites')
  const {
    data: launches,
    loading: launchesLoading,
    error: launchesError,
  } = useApi<LaunchPreview[]>('/api/launches')
  const {
    data: mapPoints,
    loading: mapLoading,
    error: mapError,
  } = useApi<MapPointsPayload>('/api/map/points')

  if (loading || satellitesLoading || launchesLoading) {
    return <LoadingState label="仪表盘同步中" />
  }
  if (error || satellitesError || launchesError) {
    return <ErrorState message={error ?? satellitesError ?? launchesError ?? ''} />
  }
  if (!data || !satellites || !launches) {
    return <EmptyState label="暂无仪表盘数据" />
  }

  const handleMapExport = async () => {
    if (!mapPoints || mapExporting) return
    setMapExporting(true)
    setMapExportError(null)
    try {
      await exportOverviewMapImage(mapPoints, now)
    } catch {
      setMapExportError('地图图片导出失败')
    } finally {
      setMapExporting(false)
    }
  }

  return (
    <div className="page-stack">
      <section className="summary-grid">
        <MetricCard
          icon={Satellite}
          label="在轨总数"
          value={data.summary.total_satellites}
          tone="blue"
        />
        <MetricCard
          icon={Activity}
          label="有效卫星"
          value={data.summary.valid_satellites}
          tone="green"
        />
        <MetricCard
          icon={AlertCircle}
          label="失效卫星"
          value={data.summary.invalid_satellites}
          tone="red"
        />
        <MetricCard
          icon={RadioTower}
          label="发射组"
          value={data.summary.launch_groups}
          tone="amber"
          meta={`已跟踪 ${formatNumber(data.summary.tracked_satellites)} 颗`}
        />
      </section>

      <div className="dashboard-grid">
        <Panel
          className="span-12"
          title="地图"
          icon={Map}
          meta={
            mapPoints
              ? `${formatNumber(mapPoints.satellites.length)} 颗`
              : undefined
          }
          action={
            <button
              className="icon-button panel-action-button"
              type="button"
              onClick={handleMapExport}
              disabled={!mapPoints || mapExporting}
              title="导出地图图片"
              aria-label="导出地图图片"
            >
              <Download size={16} />
            </button>
          }
        >
          <div className="overview-map-shell">
            <OverviewPointMap payload={mapPoints} now={now} />
            {mapLoading && <div className="overview-map-state">地图同步中</div>}
            {mapError && <div className="overview-map-state error">{mapError}</div>}
            {mapExporting && <div className="overview-map-state">图片导出中</div>}
            {mapExportError && (
              <div className="overview-map-state error">{mapExportError}</div>
            )}
          </div>
        </Panel>
        <Panel
          className="span-7"
          title="最近发射卫星"
          icon={Orbit}
          meta={formatDateTime(data.summary.last_updated_at)}
        >
          <RecentSatellitesTable satellites={satellites} scrollable linkGroups />
        </Panel>
        <Panel
          className="span-5"
          title="最近发射"
          icon={Rocket}
          meta={`${formatNumber(launches.length)} 次`}
        >
          <LaunchList launches={launches} scrollable />
        </Panel>
        <Panel className="span-6" title="制造商统计" icon={Factory}>
          <StatBars
            rows={data.manufacturers.map((item) => ({
              id: item.id,
              label: item.name,
              primary: item.satellite_count,
              secondary: `${item.group_count} 组`,
            }))}
          />
        </Panel>
        <Panel className="span-6" title="火箭统计" icon={Waypoints}>
          <StatBars
            rows={data.rockets.map((item) => ({
              id: item.id,
              label: rocketLabel(item),
              primary: item.satellite_count,
              secondary: `${item.launch_count} 次`,
            }))}
          />
        </Panel>
      </div>
    </div>
  )
}

function OrbitExplorerPage() {
  const { data: groups, loading, error } = useApi<GroupSummary[]>('/api/groups')
  const [searchParams, setSearchParams] = useSearchParams()
  const [satelliteIntl, setSatelliteIntl] = useState('')
  const requestedGroupIntl = searchParams.get('group') || ''
  const selectedGroupIntl = requestedGroupIntl || groups?.[0]?.intl_designator || ''

  const detailPath = selectedGroupIntl ? `/api/groups/${selectedGroupIntl}` : null
  const { data: detail, loading: detailLoading } = useApi<GroupDetail>(detailPath)
  const selectedSatellite = useMemo(
    () =>
      detail?.satellites.find(
        (satellite) => satellite.intl_designator === satelliteIntl,
      ) ?? null,
    [detail, satelliteIntl],
  )

  if (loading) return <LoadingState label="星组索引同步中" />
  if (error) return <ErrorState message={error} />
  if (!groups || groups.length === 0) return <EmptyState label="暂无星组数据" />

  return (
    <div className="page-stack">
      <SelectorPanel
        groups={groups}
        selectedGroup={selectedGroupIntl}
        selectedSatellite={selectedSatellite?.intl_designator ?? ''}
        satellites={detail?.satellites ?? []}
        onGroupChange={(value) => {
          setSearchParams(value ? { group: value } : {})
          setSatelliteIntl('')
        }}
        onSatelliteChange={setSatelliteIntl}
      />

      {detailLoading && <LoadingState label="轨道数据同步中" />}
      {!detailLoading && detail && !selectedSatellite && (
        <GroupDetailView detail={detail} />
      )}
      {!detailLoading && selectedSatellite && (
        <SatelliteDetailView satellite={selectedSatellite} />
      )}
    </div>
  )
}

function LaunchStatsPage() {
  const { data, loading, error } = useApi<DashboardData>('/api/dashboard')
  const {
    data: launches,
    loading: launchesLoading,
    error: launchesError,
  } = useApi<LaunchPreview[]>('/api/launches')

  if (loading || launchesLoading) return <LoadingState label="发射统计同步中" />
  if (error || launchesError) {
    return <ErrorState message={error ?? launchesError ?? ''} />
  }
  if (!data || !launches) return <EmptyState label="暂无发射统计" />

  return (
    <div className="page-stack">
      <Panel
        title="所有发射"
        icon={Rocket}
        meta={`${formatNumber(launches.length)} 次`}
      >
        <LaunchTable launches={launches} />
      </Panel>
      <div className="dashboard-grid">
        <Panel className="span-6" title="制造商" icon={Factory}>
          <StatBars
            rows={data.manufacturers.map((item) => ({
              id: item.id,
              label: item.name,
              primary: item.satellite_count,
              secondary: `${item.group_count} 组`,
            }))}
          />
        </Panel>
        <Panel className="span-6" title="火箭" icon={Waypoints}>
          <RocketTable rockets={data.rockets} />
        </Panel>
      </div>
    </div>
  )
}

function HistoryPage() {
  const { data: groups, loading, error } = useApi<GroupSummary[]>('/api/groups')
  const [groupIntl, setGroupIntl] = useState('')
  const [satelliteIntl, setSatelliteIntl] = useState('')
  const selectedGroupIntl = groupIntl || groups?.[0]?.intl_designator || ''

  const { data: detail } = useApi<GroupDetail>(
    selectedGroupIntl ? `/api/groups/${selectedGroupIntl}` : null,
  )
  const selectedSatelliteIntl =
    satelliteIntl || detail?.satellites[0]?.intl_designator || ''

  const historyPath = selectedSatelliteIntl
    ? `/api/satellites/${selectedSatelliteIntl}/history`
    : null
  const {
    data: history,
    loading: historyLoading,
    error: historyError,
  } = useApi<HistoryPoint[]>(historyPath)

  if (loading) return <LoadingState label="历史索引同步中" />
  if (error) return <ErrorState message={error} />
  if (!groups || groups.length === 0) return <EmptyState label="暂无历史数据" />

  return (
    <div className="page-stack">
      <SelectorPanel
        groups={groups}
        selectedGroup={selectedGroupIntl}
        selectedSatellite={selectedSatelliteIntl}
        satellites={detail?.satellites ?? []}
        onGroupChange={(value) => {
          setGroupIntl(value)
          setSatelliteIntl('')
        }}
        onSatelliteChange={setSatelliteIntl}
        satelliteOnly
      />
      <Panel title="近地点 / 远地点变化" icon={ChartLine}>
        {historyLoading && <LoadingState label="历史轨道同步中" compact />}
        {historyError && <ErrorState message={historyError} compact />}
        {!historyLoading && history && <HistoryChart points={history} />}
      </Panel>
    </div>
  )
}

function MapPage() {
  const now = useClock()
  const [refreshKey, setRefreshKey] = useState(0)
  const { data, loading, error } = useApi<MapPointsPayload>(
    '/api/map/satellites',
    refreshKey,
  )

  useEffect(() => {
    const id = setInterval(() => setRefreshKey((value) => value + 1), 30_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="map-page">
      <SatelliteMap payload={data} now={now} />
      <div className="map-hud">
        <div className="map-hud-main">
          <span className="hud-label">SATELLITES</span>
          <strong>{formatNumber(data?.satellites.length ?? 0)}</strong>
        </div>
        <div className="hud-meta">
          <Clock size={14} />
          <span>{formatTime(now.toISOString())}</span>
        </div>
        <button
          className="icon-button"
          type="button"
          onClick={() => setRefreshKey((value) => value + 1)}
          title="刷新 TLE"
        >
          <RefreshCw size={16} />
        </button>
      </div>
      {loading && <div className="map-state">TLE 同步中</div>}
      {error && <div className="map-state error">{error}</div>}
    </div>
  )
}

function SatelliteMap({
  payload,
  now,
}: {
  payload: MapPointsPayload | null
  now: Date
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<L.Map | null>(null)
  const trackLayerRef = useRef<L.LayerGroup | null>(null)
  const markerLayerRef = useRef<L.LayerGroup | null>(null)
  const markersRef = useRef<globalThis.Map<string, L.CircleMarker>>(
    new globalThis.Map(),
  )
  const satelliteByKeyRef = useRef<
    globalThis.Map<string, MapSatellitePoint>
  >(new globalThis.Map())
  const hoverClearTimerRef = useRef<ReturnType<typeof window.setTimeout> | null>(
    null,
  )
  const mapFittedRef = useRef(false)
  const [mapError, setMapError] = useState<string | null>(null)
  const [activeGroupKey, setActiveGroupKey] = useState<string | null>(null)
  const trackMinute = Math.floor(now.getTime() / 60_000)
  const tleKey =
    payload?.satellites
      .map(
        (satellite) =>
          `${satellite.id ?? satellite.intl_designator}:${satellite.raw_tle}`,
      )
      .join('|') ?? ''

  const clearHoverTimer = useCallback(() => {
    if (hoverClearTimerRef.current !== null) {
      window.clearTimeout(hoverClearTimerRef.current)
      hoverClearTimerRef.current = null
    }
  }, [])

  const activateSatelliteGroup = useCallback(
    (satellite: MapSatellitePoint) => {
      clearHoverTimer()
      const groupKey = satelliteGroupKey(satellite)
      setActiveGroupKey(groupKey)
    },
    [clearHoverTimer],
  )

  const scheduleDeactivateSatelliteGroup = useCallback(() => {
    clearHoverTimer()
    hoverClearTimerRef.current = window.setTimeout(() => {
      setActiveGroupKey(null)
      hoverClearTimerRef.current = null
    }, 120)
  }, [clearHoverTimer])

  useEffect(() => {
    if (!containerRef.current) {
      return
    }

    const map = L.map(containerRef.current, {
      center: [25, 105],
      zoom: 2,
      minZoom: 2,
      maxZoom: 10,
      worldCopyJump: true,
      zoomControl: false,
    })

    map.attributionControl.setPrefix(false)
    L.control.zoom({ position: 'bottomright' }).addTo(map)
    L.tileLayer(GAODE_STANDARD_TILE_URL, {
      subdomains: ['1', '2', '3', '4'],
      minZoom: 2,
      maxZoom: 10,
      attribution: '© 高德地图',
    })
      .on('tileerror', () => setMapError('高德标准瓦片加载失败'))
      .on('load', () => setMapError(null))
      .addTo(map)

    const trackLayer = L.layerGroup().addTo(map)
    const markerLayer = L.layerGroup().addTo(map)
    const markerStore = markersRef.current
    const satelliteStore = satelliteByKeyRef.current
    mapRef.current = map
    trackLayerRef.current = trackLayer
    markerLayerRef.current = markerLayer

    return () => {
      clearHoverTimer()
      map.remove()
      markerStore.clear()
      satelliteStore.clear()
      mapRef.current = null
      trackLayerRef.current = null
      markerLayerRef.current = null
    }
  }, [clearHoverTimer])

  useEffect(() => {
    mapFittedRef.current = false
  }, [tleKey])

  useEffect(() => {
    const trackLayer = trackLayerRef.current
    if (!trackLayer) return

    trackLayer.clearLayers()
    if (!payload || !activeGroupKey) return

    const trackMoment = new Date(trackMinute * 60_000)
    payload.satellites.forEach((satellite, index) => {
      if (satelliteGroupKey(satellite) !== activeGroupKey) return

      const color = LEO_TRACK_COLORS[index % LEO_TRACK_COLORS.length]
      const track = generatePreviousOrbitTrack(satellite.raw_tle, trackMoment)
      splitTrackByDateline(track).forEach((segment) => {
        L.polyline(segment, {
          color,
          opacity: 0.72,
          weight: 1.8,
          lineJoin: 'round',
          interactive: false,
        }).addTo(trackLayer)
      })
    })
  }, [activeGroupKey, payload, trackMinute])

  useEffect(() => {
    const map = mapRef.current
    const markerLayer = markerLayerRef.current
    if (!map || !markerLayer || !payload) return

    const bounds = L.latLngBounds([])
    const visibleKeys = new Set<string>()
    satelliteByKeyRef.current.clear()

    payload.satellites.forEach((satellite, index) => {
      const key = satelliteMarkerKey(satellite)
      satelliteByKeyRef.current.set(key, satellite)
      const position = propagateTlePosition(satellite.raw_tle, now)
      if (!position) return

      visibleKeys.add(key)
      const color = LEO_TRACK_COLORS[index % LEO_TRACK_COLORS.length]
      const latLng = pointToLatLng(position)
      let marker = markersRef.current.get(key)
      if (!marker) {
        marker = L.circleMarker(latLng, {
          radius: 4,
          color: '#ffffff',
          weight: 1.3,
          fillColor: color,
          fillOpacity: 0.96,
        }).addTo(markerLayer)
        marker.bindTooltip(satelliteMapTooltip(satellite), {
          direction: 'top',
          offset: [0, -8],
        })
        marker.on('mouseover', () => {
          const currentSatellite = satelliteByKeyRef.current.get(key)
          if (currentSatellite) {
            activateSatelliteGroup(currentSatellite)
          }
        })
        marker.on('mouseout', scheduleDeactivateSatelliteGroup)
        markersRef.current.set(key, marker)
      } else {
        marker.setLatLng(latLng)
        marker.setTooltipContent(satelliteMapTooltip(satellite))
      }

      const isActiveGroup =
        activeGroupKey !== null && satelliteGroupKey(satellite) === activeGroupKey
      marker.setRadius(isActiveGroup ? 4.8 : 4)
      marker.setStyle({
        color: '#ffffff',
        weight: isActiveGroup ? 1.8 : 1.3,
        fillColor: color,
        fillOpacity: isActiveGroup ? 1 : 0.96,
      })
      if (isActiveGroup) {
        marker.openTooltip()
      } else {
        marker.closeTooltip()
      }
      bounds.extend(latLng)
    })

    markersRef.current.forEach((marker, key) => {
      if (!visibleKeys.has(key)) {
        marker.remove()
        markersRef.current.delete(key)
      }
    })

    if (bounds.isValid()) {
      if (!mapFittedRef.current) {
        map.fitBounds(bounds, { padding: [80, 80], maxZoom: 3 })
        mapFittedRef.current = true
      }
    } else {
      map.setView([25, 105], 2)
    }
  }, [
    activateSatelliteGroup,
    activeGroupKey,
    now,
    payload,
    scheduleDeactivateSatelliteGroup,
  ])

  return (
    <>
      <div ref={containerRef} className="tile-map-container" />
      {mapError && <div className="map-error-note">{mapError}</div>}
    </>
  )
}

function OverviewPointMap({
  payload,
  now,
}: {
  payload: MapPointsPayload | null
  now: Date
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<L.Map | null>(null)
  const overlayLayerRef = useRef<L.LayerGroup | null>(null)
  const [mapError, setMapError] = useState<string | null>(null)

  useEffect(() => {
    if (!containerRef.current) {
      return
    }

    const map = L.map(containerRef.current, {
      center: [25, 105],
      zoom: 2,
      minZoom: 2,
      maxZoom: 2,
      worldCopyJump: true,
      zoomControl: false,
      dragging: false,
      touchZoom: false,
      scrollWheelZoom: false,
      doubleClickZoom: false,
      boxZoom: false,
      keyboard: false,
    })

    map.attributionControl.setPrefix(false)
    L.tileLayer(GAODE_STANDARD_TILE_URL, {
      subdomains: ['1', '2', '3', '4'],
      minZoom: 2,
      maxZoom: 2,
      attribution: '© 高德地图',
    })
      .on('tileerror', () => setMapError('高德标准瓦片加载失败'))
      .on('load', () => setMapError(null))
      .addTo(map)

    const overlayLayer = L.layerGroup().addTo(map)
    mapRef.current = map
    overlayLayerRef.current = overlayLayer

    return () => {
      map.remove()
      mapRef.current = null
      overlayLayerRef.current = null
    }
  }, [])

  useEffect(() => {
    const overlayLayer = overlayLayerRef.current
    if (!overlayLayer || !payload) return

    overlayLayer.clearLayers()
    payload.satellites.forEach((satellite) => {
      const position = propagateTlePosition(satellite.raw_tle, now)
      if (!position) return

      const color = isHighOrbitSatellite(satellite)
        ? OVERVIEW_MAP_HIGH_ORBIT_COLOR
        : OVERVIEW_MAP_DEFAULT_COLOR
      const marker = L.circleMarker(pointToLatLng(position), {
        radius: 3.6,
        color: '#ffffff',
        weight: 1.2,
        fillColor: color,
        fillOpacity: 0.95,
      }).addTo(overlayLayer)
      marker.bindTooltip(
        `${satellite.group_name ?? '-'}<br>${satellite.intl_designator}`,
        { direction: 'top', offset: [0, -7] },
      )
    })
  }, [payload, now])

  return (
    <>
      <div ref={containerRef} className="tile-map-container" />
      {mapError && <div className="map-error-note">{mapError}</div>}
    </>
  )
}

function SelectorPanel({
  groups,
  selectedGroup,
  selectedSatellite,
  satellites,
  onGroupChange,
  onSatelliteChange,
  satelliteOnly = false,
}: {
  groups: GroupSummary[]
  selectedGroup: string
  selectedSatellite: string
  satellites: SatellitePreview[]
  onGroupChange: (value: string) => void
  onSatelliteChange: (value: string) => void
  satelliteOnly?: boolean
}) {
  return (
    <Panel title="对象选择" icon={Search} dense>
      <div className="selector-grid">
        <label className="field">
          <span>星组</span>
          <select
            value={selectedGroup}
            onChange={(event) => onGroupChange(event.target.value)}
          >
            {groups.map((group) => (
              <option key={group.intl_designator} value={group.intl_designator}>
                {group.name} · {group.intl_designator}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>卫星</span>
          <select
            value={selectedSatellite}
            onChange={(event) => onSatelliteChange(event.target.value)}
          >
            {!satelliteOnly && <option value="">整组</option>}
            {satellites.map((satellite) => (
              <option
                key={satellite.intl_designator}
                value={satellite.intl_designator}
              >
                {satellite.intl_designator}
              </option>
            ))}
          </select>
        </label>
      </div>
    </Panel>
  )
}

function GroupDetailView({ detail }: { detail: GroupDetail }) {
  return (
    <div className="dashboard-grid">
      <Panel className="span-4" title={detail.name} icon={ListTree}>
        <InfoGrid
          rows={[
            ['国际识别号', detail.intl_designator],
            ['卫星数量', formatNumber(detail.satellite_count)],
            ['有效 / 失效', `${detail.valid_satellite_count} / ${detail.invalid_satellite_count}`],
            ['发射时间', formatLaunchDateTime(detail.launch_time)],
            ['发射场', detail.launch_site ?? '-'],
            ['火箭', rocketName(detail)],
            ['制造商', detail.manufacturer_name ?? '-'],
          ]}
        />
      </Panel>
      <Panel className="span-8" title="组内卫星" icon={Satellite}>
        <RecentSatellitesTable satellites={detail.satellites} />
      </Panel>
      <Panel className="span-12" title="组轨道概览" icon={Orbit}>
        <OrbitTiles orbit={detail.orbit} />
      </Panel>
    </div>
  )
}

function SatelliteDetailView({ satellite }: { satellite: SatellitePreview }) {
  return (
    <div className="dashboard-grid">
      <Panel className="span-5" title={satellite.intl_designator} icon={Satellite}>
        <InfoGrid
          rows={[
            ['状态', satellite.status],
            ['所属星组', satellite.group_name ?? '-'],
            ['组识别号', satellite.group_intl_designator ?? '-'],
            ['TLE 历元', formatDateTime(satellite.epoch_at)],
            ['发射时间', formatLaunchDateTime(satellite.launch_time)],
            ['发射场', satellite.launch_site ?? '-'],
            ['火箭', rocketName(satellite)],
            ['制造商', satellite.manufacturer_name ?? '-'],
          ]}
        />
      </Panel>
      <Panel className="span-7" title="当前轨道" icon={Orbit}>
        <OrbitTiles orbit={satellite.orbit} />
      </Panel>
    </div>
  )
}

function HistoryChart({ points }: { points: HistoryPoint[] }) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const chartPoints = points.filter(
    (point) => point.perigee_km !== null && point.apogee_km !== null,
  )
  if (chartPoints.length === 0) return <EmptyState label="暂无可绘制历史轨道" compact />

  const width = 820
  const height = 280
  const values = chartPoints.flatMap((point) => [
    point.perigee_km ?? 0,
    point.apogee_km ?? 0,
  ])
  const axis = createAdaptiveKmAxis(values)
  const longestYAxisLabel = Math.max(
    ...axis.ticks.map((tick) => formatAxisKm(tick).length),
  )
  const padding = {
    top: 22,
    right: 28,
    bottom: 42,
    left: Math.min(96, Math.max(58, longestYAxisLabel * 7 + 16)),
  }
  const plotWidth = width - padding.left - padding.right
  const plotHeight = height - padding.top - padding.bottom
  const xLabelStep = Math.max(1, Math.ceil(chartPoints.length / 8))
  const xFor = (index: number) =>
    padding.left + (plotWidth * index) / Math.max(chartPoints.length - 1, 1)
  const yFor = (value: number) =>
    padding.top +
    plotHeight -
    ((value - axis.min) / Math.max(axis.max - axis.min, 1)) * plotHeight
  const pathFor = (field: 'perigee_km' | 'apogee_km') =>
    chartPoints
      .map((point, index) => {
        const value = point[field] ?? 0
        return `${index === 0 ? 'M' : 'L'} ${xFor(index).toFixed(2)} ${yFor(value).toFixed(2)}`
      })
      .join(' ')
  const activeIndex =
    hoverIndex === null
      ? null
      : Math.min(Math.max(hoverIndex, 0), chartPoints.length - 1)
  const activePoint = activeIndex === null ? null : chartPoints[activeIndex]
  const tooltipWidth = 168
  const tooltipHeight = 68
  const tooltipX =
    activeIndex === null
      ? 0
      : Math.min(
          width - padding.right - tooltipWidth,
          Math.max(padding.left + 8, xFor(activeIndex) + 12),
        )
  const tooltipY =
    activePoint === null
      ? 0
      : Math.min(
          height - padding.bottom - tooltipHeight - 8,
          Math.max(
            padding.top + 8,
            Math.min(
              yFor(activePoint.apogee_km ?? 0),
              yFor(activePoint.perigee_km ?? 0),
            ) - 18,
          ),
        )
  const handlePointerMove = (event: PointerEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect()
    const viewX = ((event.clientX - rect.left) / rect.width) * width
    const ratio = Math.min(1, Math.max(0, (viewX - padding.left) / plotWidth))
    setHoverIndex(Math.round(ratio * Math.max(chartPoints.length - 1, 0)))
  }

  return (
    <div className="chart-wrap">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="历史轨道折线图"
        onPointerMove={handlePointerMove}
        onPointerLeave={() => setHoverIndex(null)}
      >
        <line
          x1={padding.left}
          y1={height - padding.bottom}
          x2={width - padding.right}
          y2={height - padding.bottom}
          className="chart-axis"
        />
        <line
          x1={padding.left}
          y1={padding.top}
          x2={padding.left}
          y2={height - padding.bottom}
          className="chart-axis"
        />
        {axis.ticks.map((value) => {
          const y = yFor(value)
          return (
            <g key={value}>
              <line
                x1={padding.left}
                y1={y}
                x2={width - padding.right}
                y2={y}
                className="chart-grid"
              />
              <text x={12} y={y + 4} className="chart-label">
                {formatAxisKm(value)}
              </text>
            </g>
          )
        })}
        <path d={pathFor('apogee_km')} className="chart-line apogee" />
        <path d={pathFor('perigee_km')} className="chart-line perigee" />
        {chartPoints.map((point, index) => (
          <g key={point.id}>
            <circle
              cx={xFor(index)}
              cy={yFor(point.apogee_km ?? 0)}
              r="3.5"
              className="chart-dot apogee"
            />
            <circle
              cx={xFor(index)}
              cy={yFor(point.perigee_km ?? 0)}
              r="3.5"
              className="chart-dot perigee"
            />
            {(index % xLabelStep === 0 || index === chartPoints.length - 1) && (
              <text
                x={xFor(index)}
                y={height - 15}
                textAnchor="middle"
                className="chart-date"
              >
                {formatShortDate(point.epoch_at)}
              </text>
            )}
          </g>
        ))}
        {activePoint && activeIndex !== null && (
          <>
            <line
              x1={xFor(activeIndex)}
              y1={padding.top}
              x2={xFor(activeIndex)}
              y2={height - padding.bottom}
              className="chart-hover-line"
            />
            <circle
              cx={xFor(activeIndex)}
              cy={yFor(activePoint.apogee_km ?? 0)}
              r="6"
              className="chart-dot apogee active"
            />
            <circle
              cx={xFor(activeIndex)}
              cy={yFor(activePoint.perigee_km ?? 0)}
              r="6"
              className="chart-dot perigee active"
            />
            <g className="chart-tooltip" transform={`translate(${tooltipX} ${tooltipY})`}>
              <rect width={tooltipWidth} height={tooltipHeight} rx="7" />
              <text x="12" y="19" className="chart-tooltip-title">
                {formatDateTime(activePoint.epoch_at)}
              </text>
              <text x="12" y="40" className="chart-tooltip-apogee">
                远地点 {formatKm(activePoint.apogee_km)}
              </text>
              <text x="12" y="58" className="chart-tooltip-perigee">
                近地点 {formatKm(activePoint.perigee_km)}
              </text>
            </g>
          </>
        )}
        <rect
          x={padding.left}
          y={padding.top}
          width={plotWidth}
          height={plotHeight}
          className="chart-hit-area"
        />
      </svg>
      <div className="legend-row">
        <span className="legend-item apogee">远地点</span>
        <span className="legend-item perigee">近地点</span>
      </div>
    </div>
  )
}

function RecentSatellitesTable({
  satellites,
  scrollable = false,
  linkGroups = false,
}: {
  satellites: SatellitePreview[]
  scrollable?: boolean
  linkGroups?: boolean
}) {
  if (satellites.length === 0) return <EmptyState label="暂无卫星数据" compact />
  return (
    <div className={`table-wrap${scrollable ? ' overview-scroll-wrap' : ''}`}>
      <table>
        <thead>
          <tr>
            <th>国际识别号</th>
            <th>组名称</th>
            <th>倾角</th>
            <th>近地点</th>
            <th>远地点</th>
            <th>离心率</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          {satellites.map((satellite) => (
            <tr key={`${satellite.group_intl_designator}-${satellite.intl_designator}`}>
              <td className="mono">
                {linkGroups && satellite.group_intl_designator ? (
                  <Link
                    className="inline-link mono-link"
                    to={groupExplorerPath(satellite.group_intl_designator)}
                  >
                    {satellite.intl_designator}
                  </Link>
                ) : (
                  satellite.intl_designator
                )}
              </td>
              <td>
                {linkGroups && satellite.group_intl_designator ? (
                  <Link
                    className="inline-link"
                    to={groupExplorerPath(satellite.group_intl_designator)}
                  >
                    {satellite.group_name ?? satellite.group_intl_designator}
                  </Link>
                ) : (
                  satellite.group_name ?? '-'
                )}
              </td>
              <td>{formatDegree(satellite.orbit.inclination_deg)}</td>
              <td>{formatKm(satellite.orbit.perigee_km)}</td>
              <td>{formatKm(satellite.orbit.apogee_km)}</td>
              <td>{formatEccentricity(satellite.orbit.eccentricity)}</td>
              <td>
                <StatusBadge status={satellite.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function LaunchTable({ launches }: { launches: LaunchPreview[] }) {
  if (launches.length === 0) return <EmptyState label="暂无发射数据" compact />
  return (
    <div className="table-wrap launch-table-wrap">
      <table>
        <thead>
          <tr>
            <th>发射时间</th>
            <th>组名称</th>
            <th>轨道</th>
            <th>发射场</th>
            <th>火箭</th>
            <th>卫星制造商</th>
            <th>卫星数</th>
          </tr>
        </thead>
        <tbody>
          {launches.map((launch) => (
            <tr key={launch.intl_designator}>
              <td>{formatLaunchDateTime(launch.launch_time)}</td>
              <td>{launch.name ?? launch.intl_designator}</td>
              <td>{orbitSentence(launch.orbit)}</td>
              <td>{launch.launch_site ?? '-'}</td>
              <td>{rocketName(launch)}</td>
              <td>{launch.manufacturer_name ?? '-'}</td>
              <td>{formatNumber(launch.satellite_count)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RocketTable({ rockets }: { rockets: RocketStat[] }) {
  if (rockets.length === 0) return <EmptyState label="暂无火箭统计" compact />
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>火箭</th>
            <th>发射次数</th>
            <th>部署卫星</th>
          </tr>
        </thead>
        <tbody>
          {rockets.map((rocket) => (
            <tr key={rocket.id}>
              <td>{rocketLabel(rocket)}</td>
              <td>{formatNumber(rocket.launch_count)}</td>
              <td>{formatNumber(rocket.satellite_count)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function LaunchList({
  launches,
  scrollable = false,
}: {
  launches: LaunchPreview[]
  scrollable?: boolean
}) {
  if (launches.length === 0) return <EmptyState label="暂无发射数据" compact />
  return (
    <div className={`launch-list${scrollable ? ' overview-scroll-wrap' : ''}`}>
      {launches.map((launch) => (
        <div key={launch.intl_designator} className="launch-item">
          <div>
            <strong>
              <Link className="inline-link" to={groupExplorerPath(launch.intl_designator)}>
                {launch.name ?? launch.intl_designator}
              </Link>
            </strong>
            <span>{formatLaunchDateTime(launch.launch_time)}</span>
          </div>
          <small>{rocketName(launch)}</small>
        </div>
      ))}
    </div>
  )
}

function StatBars({
  rows,
}: {
  rows: { id: number; label: string; primary: number; secondary: string }[]
}) {
  if (rows.length === 0) return <EmptyState label="暂无统计数据" compact />
  const maxValue = Math.max(...rows.map((row) => row.primary), 1)
  return (
    <div className="stat-bars">
      {rows.slice(0, 8).map((row) => (
        <div key={row.id} className="stat-row">
          <div className="stat-row-head">
            <span>{row.label}</span>
            <strong>{formatNumber(row.primary)}</strong>
          </div>
          <div className="bar-track">
            <span style={{ width: `${(row.primary / maxValue) * 100}%` }} />
          </div>
          <small>{row.secondary}</small>
        </div>
      ))}
    </div>
  )
}

function OrbitTiles({ orbit }: { orbit: OrbitSummary }) {
  return (
    <div className="orbit-tiles">
      <MetricInline label="轨道倾角" value={formatDegree(orbit.inclination_deg)} />
      <MetricInline label="近地点" value={formatKm(orbit.perigee_km)} />
      <MetricInline label="远地点" value={formatKm(orbit.apogee_km)} />
      <MetricInline
        label="离心率"
        value={formatEccentricity(orbit.eccentricity)}
      />
    </div>
  )
}

function InfoGrid({ rows }: { rows: [string, string | number][] }) {
  return (
    <dl className="info-grid">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  )
}

function MetricCard({
  icon: Icon,
  label,
  value,
  meta,
  tone,
}: {
  icon: IconComponent
  label: string
  value: number
  meta?: string
  tone: 'blue' | 'green' | 'red' | 'amber'
}) {
  return (
    <article className={`metric-card ${tone}`}>
      <Icon size={20} />
      <div>
        <span>{label}</span>
        <strong>{formatNumber(value)}</strong>
        {meta && <small>{meta}</small>}
      </div>
    </article>
  )
}

function MetricInline({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-inline">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function Panel({
  title,
  icon: Icon,
  children,
  className = '',
  dense = false,
  meta,
  action,
}: {
  title: string
  icon: IconComponent
  children: React.ReactNode
  className?: string
  dense?: boolean
  meta?: string
  action?: React.ReactNode
}) {
  return (
    <section className={`panel ${dense ? 'dense' : ''} ${className}`}>
      <header className="panel-header">
        <div>
          <Icon size={17} />
          <h2>{title}</h2>
        </div>
        {(meta || action) && (
          <div className="panel-header-actions">
            {meta && <span>{meta}</span>}
            {action}
          </div>
        )}
      </header>
      {children}
    </section>
  )
}

function StatusBadge({ status }: { status: string }) {
  const valid = status === '有效'
  return (
    <span className={`status-badge ${valid ? 'valid' : 'invalid'}`}>
      <CircleDot size={12} />
      {status}
    </span>
  )
}

function LoadingState({
  label,
  compact = false,
}: {
  label: string
  compact?: boolean
}) {
  return <div className={`state ${compact ? 'compact' : ''}`}>{label}</div>
}

function ErrorState({
  message,
  compact = false,
}: {
  message: string
  compact?: boolean
}) {
  return (
    <div className={`state error ${compact ? 'compact' : ''}`}>
      <AlertCircle size={18} />
      <span>{message}</span>
    </div>
  )
}

function EmptyState({
  label,
  compact = false,
}: {
  label: string
  compact?: boolean
}) {
  return <div className={`state empty ${compact ? 'compact' : ''}`}>{label}</div>
}

function App() {
  const now = useClock()
  const [noticeDismissed, setNoticeDismissed] = useState(false)
  const [noticeClosing, setNoticeClosing] = useState(false)
  return (
    <BrowserRouter>
      <div className={`app ${noticeDismissed ? 'notice-hidden' : 'notice-visible'}`}>
        {!noticeDismissed && (
          <div
            className={`public-data-notice${noticeClosing ? ' closing' : ''}`}
            role="status"
            onAnimationEnd={() => {
              if (noticeClosing) {
                setNoticeDismissed(true)
              }
            }}
          >
            <span>数据均来自公开信息，仅供学习参考。</span>
            <a
              href="https://github.com/NearlyHeadlessJack/gw-dashboard"
              target="_blank"
              rel="noreferrer"
            >
              <svg
                className="github-mark"
                viewBox="0 0 16 16"
                aria-hidden="true"
                focusable="false"
              >
                <path d="M8 0C3.58 0 0 3.69 0 8.24c0 3.64 2.29 6.73 5.47 7.82.4.08.55-.18.55-.4 0-.2-.01-.85-.01-1.54-2.01.38-2.53-.5-2.69-.96-.09-.24-.48-.96-.82-1.15-.28-.16-.68-.55-.01-.56.63-.01 1.08.6 1.23.85.72 1.25 1.87.9 2.33.69.07-.54.28-.9.51-1.11-1.78-.21-3.64-.92-3.64-4.07 0-.9.31-1.64.82-2.22-.08-.21-.36-1.05.08-2.19 0 0 .67-.22 2.2.85A7.38 7.38 0 0 1 8 3.97c.68 0 1.36.09 2 .28 1.53-1.07 2.2-.85 2.2-.85.44 1.14.16 1.98.08 2.19.51.58.82 1.32.82 2.22 0 3.16-1.87 3.86-3.65 4.07.29.26.54.75.54 1.52 0 1.1-.01 1.98-.01 2.25 0 .22.15.49.55.4A8.15 8.15 0 0 0 16 8.24C16 3.69 12.42 0 8 0Z" />
              </svg>
              项目主页
            </a>
            <button
              className="notice-close"
              type="button"
              onClick={() => setNoticeClosing(true)}
              disabled={noticeClosing}
              aria-label="关闭通知"
              title="关闭通知"
            >
              <X size={15} />
            </button>
          </div>
        )}
        <header className="top-nav">
          <div className="nav-brand">
            <Crosshair size={19} />
            <span className="brand-text">星网</span>
            <span className="brand-sub">GW DASHBOARD</span>
          </div>
          <nav className="nav-tabs" aria-label="Primary navigation">
            <NavLink
              to="/dashboard"
              className={({ isActive }) => `tab${isActive ? ' active' : ''}`}
            >
              <LayoutDashboard size={16} />
              仪表盘
            </NavLink>
            <NavLink
              to="/map"
              className={({ isActive }) => `tab${isActive ? ' active' : ''}`}
            >
              <Map size={16} />
              地图
            </NavLink>
          </nav>
          <div className="nav-time">
            <span>UTC</span>
            <strong>{now.toISOString().slice(11, 19)}</strong>
          </div>
          <div className="nav-time">
            <span>BJT</span>
            <strong>
              {now.toLocaleTimeString('zh-CN', {
                timeZone: 'Asia/Shanghai',
                hour12: false,
              })}
            </strong>
          </div>
        </header>
        <div className="app-body">
          <Routes>
            <Route path="/dashboard/*" element={<DashboardLayout />} />
            <Route path="/map" element={<MapPage />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  )
}

async function exportOverviewMapImage(
  payload: MapPointsPayload,
  now: Date,
): Promise<void> {
  const canvas = document.createElement('canvas')
  canvas.width = EXPORT_MAP_WIDTH
  canvas.height = EXPORT_MAP_HEIGHT
  const context = canvas.getContext('2d')
  if (!context) {
    throw new Error('Canvas is not available')
  }

  await drawExportWorldMap(context, canvas.width, canvas.height)

  const points = payload.satellites
    .map((satellite) => ({
      satellite,
      position: propagateTlePosition(satellite.raw_tle, now),
    }))
    .filter(
      (
        item,
      ): item is {
        satellite: MapSatellitePoint
        position: GeoPoint
      } => item.position !== null,
    )

  drawExportSatellitePoints(context, points, canvas.width, canvas.height)
  drawExportMapCaption(context, points.length, now)

  const blob = await canvasToPngBlob(canvas)
  const filename = `gw-satellite-map-${now
    .toISOString()
    .replaceAll(':', '')
    .replaceAll('.', '-')}.png`
  downloadBlob(blob, filename)
}

async function drawExportWorldMap(
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
): Promise<void> {
  context.fillStyle = '#dbe8f4'
  context.fillRect(0, 0, width, height)

  const tileCount = 2 ** EXPORT_MAP_ZOOM
  const tileResults = await Promise.allSettled(
    Array.from({ length: tileCount * tileCount }, (_, index) => {
      const x = index % tileCount
      const y = Math.floor(index / tileCount)
      return loadExportTileImage(x, y, EXPORT_MAP_ZOOM)
    }),
  )

  let loadedTileCount = 0
  tileResults.forEach((result) => {
    if (result.status !== 'fulfilled') return

    loadedTileCount += 1
    const tileWidth = width / tileCount
    const tileHeight = height / tileCount
    context.drawImage(
      result.value.image,
      result.value.x * tileWidth,
      result.value.y * tileHeight,
      tileWidth,
      tileHeight,
    )
  })

  if (loadedTileCount === 0) {
    throw new Error('Map tiles failed to load')
  }
}

function loadExportTileImage(
  x: number,
  y: number,
  z: number,
): Promise<{ image: HTMLImageElement; x: number; y: number }> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.crossOrigin = 'anonymous'
    image.onload = () => resolve({ image, x, y })
    image.onerror = () => reject(new Error('Map tile failed to load'))
    image.src = gaodeTileUrl(x, y, z)
  })
}

function gaodeTileUrl(x: number, y: number, z: number): string {
  const subdomain = String(((x + y) % 4) + 1)
  return GAODE_STANDARD_TILE_URL.replace('{s}', subdomain)
    .replace('{x}', String(x))
    .replace('{y}', String(y))
    .replace('{z}', String(z))
}

function drawExportSatellitePoints(
  context: CanvasRenderingContext2D,
  points: Array<{ satellite: MapSatellitePoint; position: GeoPoint }>,
  width: number,
  height: number,
) {
  points.forEach(({ satellite, position }) => {
    const projected = projectGeoPointForExport(position, width, height)
    const highOrbit = isHighOrbitSatellite(satellite)
    context.beginPath()
    context.arc(projected.x, projected.y, highOrbit ? 5 : 4, 0, Math.PI * 2)
    context.fillStyle = highOrbit
      ? OVERVIEW_MAP_HIGH_ORBIT_COLOR
      : OVERVIEW_MAP_DEFAULT_COLOR
    context.fill()
    context.lineWidth = 1.6
    context.strokeStyle = '#ffffff'
    context.stroke()
  })
}

function drawExportMapCaption(
  context: CanvasRenderingContext2D,
  satelliteCount: number,
  now: Date,
) {
  const iso = now.toISOString()
  const timestamp = `${iso.slice(0, 10)} ${iso.slice(11, 19)}Z`
  context.save()
  context.fillStyle = 'rgba(255, 255, 255, 0.9)'
  context.fillRect(24, 24, 350, 64)
  context.fillStyle = '#172033'
  context.font = '700 19px system-ui, -apple-system, BlinkMacSystemFont, sans-serif'
  context.fillText('星网卫星位置图', 42, 52)
  context.font = '500 14px system-ui, -apple-system, BlinkMacSystemFont, sans-serif'
  context.fillText(`${formatNumber(satelliteCount)} 颗 · ${timestamp}`, 42, 76)
  context.restore()
}

function projectGeoPointForExport(
  point: GeoPoint,
  width: number,
  height: number,
): { x: number; y: number } {
  const latitude = Math.max(
    -EXPORT_MERCATOR_MAX_LAT,
    Math.min(EXPORT_MERCATOR_MAX_LAT, point.latitude),
  )
  const longitude = normalizeLongitude(point.longitude)
  const sinLatitude = Math.sin((latitude * Math.PI) / 180)
  return {
    x: ((longitude + 180) / 360) * width,
    y:
      (0.5 -
        Math.log((1 + sinLatitude) / (1 - sinLatitude)) / (4 * Math.PI)) *
      height,
  }
}

function normalizeLongitude(value: number): number {
  return ((((value + 180) % 360) + 360) % 360) - 180
}

function canvasToPngBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) {
        resolve(blob)
      } else {
        reject(new Error('Canvas export failed'))
      }
    }, 'image/png')
  })
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

function pointToLatLng(point: GeoPoint): L.LatLngTuple {
  return [point.latitude, point.longitude]
}

function splitTrackByDateline(track: GeoPoint[]): L.LatLngTuple[][] {
  const segments: L.LatLngTuple[][] = []
  let currentSegment: L.LatLngTuple[] = []
  let previousLongitude: number | null = null

  track.forEach((point) => {
    if (
      previousLongitude !== null &&
      Math.abs(point.longitude - previousLongitude) > 180
    ) {
      if (currentSegment.length > 1) {
        segments.push(currentSegment)
      }
      currentSegment = []
    }
    currentSegment.push(pointToLatLng(point))
    previousLongitude = point.longitude
  })

  if (currentSegment.length > 1) {
    segments.push(currentSegment)
  }
  return segments
}

function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-'
  return new Intl.NumberFormat('zh-CN').format(value)
}

function formatKm(value: number | null): string {
  if (value === null) return '-'
  return `${Math.round(value).toLocaleString('zh-CN')} km`
}

function formatAxisKm(value: number): string {
  return `${Math.round(value).toLocaleString('zh-CN')} km`
}

function createAdaptiveKmAxis(values: number[]) {
  const rawMin = Math.min(...values)
  const rawMax = Math.max(...values)
  const spread = rawMax - rawMin
  const fallbackSpread = Math.max(Math.abs(rawMax) * 0.02, 20)
  const paddedMin = rawMin - (spread > 0 ? spread * 0.08 : fallbackSpread / 2)
  const paddedMax = rawMax + (spread > 0 ? spread * 0.08 : fallbackSpread / 2)
  const tickCount = 5
  const step = Math.max(1, niceNumber((paddedMax - paddedMin) / (tickCount - 1)))
  let min = Math.floor(paddedMin / step) * step
  const max = Math.ceil(paddedMax / step) * step

  if (rawMin >= 0 && min < 0) min = 0

  const ticks: number[] = []
  for (let value = min; value <= max + step * 0.5; value += step) {
    ticks.push(Number(value.toFixed(6)))
  }

  return { min, max, ticks }
}

function niceNumber(value: number): number {
  if (!Number.isFinite(value) || value <= 0) return 1
  const exponent = Math.floor(Math.log10(value))
  const fraction = value / 10 ** exponent
  const niceFraction =
    fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10
  return niceFraction * 10 ** exponent
}

function formatDegree(value: number | null): string {
  if (value === null) return '-'
  return `${value.toFixed(2)}°`
}

function formatEccentricity(value: number | null): string {
  if (value === null) return '-'
  return value.toFixed(6)
}

function formatDateTime(value: string | null): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function formatLaunchDateTime(value: string | null): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function formatShortDate(value: string | null): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return `${date.getMonth() + 1}/${date.getDate()}`
}

function formatTime(value: string | null | undefined): string {
  if (!value) return '---- -- -- --:--:--Z'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '---- -- -- --:--:--Z'
  const iso = date.toISOString()
  return `${iso.slice(0, 10)} ${iso.slice(11, 19)}Z`
}

function rocketName(
  value: Pick<LaunchPreview, 'rocket_name' | 'rocket_serial_number'>,
): string {
  if (!value.rocket_name) return '-'
  return value.rocket_serial_number
    ? `${value.rocket_name} ${value.rocket_serial_number}`
    : value.rocket_name
}

function rocketLabel(rocket: RocketStat): string {
  return rocket.name
}

function groupExplorerPath(intlDesignator: string): string {
  return `/dashboard/orbits?group=${encodeURIComponent(intlDesignator)}`
}

function orbitSentence(orbit: OrbitSummary): string {
  return `${formatDegree(orbit.inclination_deg)} / ${formatKm(
    orbit.perigee_km,
  )} - ${formatKm(orbit.apogee_km)}`
}

function satelliteMarkerKey(satellite: MapSatellitePoint): string {
  return satellite.intl_designator
}

function satelliteGroupKey(satellite: MapSatellitePoint): string {
  if (satellite.group_intl_designator) return satellite.group_intl_designator
  if (satellite.group_id !== null) return `group:${satellite.group_id}`
  if (satellite.group_name) return `group:${satellite.group_name}`
  return `satellite:${satellite.intl_designator}`
}

function satelliteMapTooltip(satellite: MapSatellitePoint): string {
  const labelName = satellite.group_name ?? satellite.group_intl_designator ?? '-'
  const lines = [labelName, mapTooltipIdentifier(satellite)]
  if (
    satellite.orbit.perigee_km !== null ||
    satellite.orbit.apogee_km !== null
  ) {
    lines.push(
      `${formatKm(satellite.orbit.perigee_km)} × ${formatKm(
        satellite.orbit.apogee_km,
      )}`,
    )
  }
  return lines.join('<br>')
}

function mapTooltipIdentifier(group: { intl_designator: string; orbit_type: string }): string {
  return group.orbit_type === 'geo'
    ? `${group.intl_designator} · GEO`
    : group.intl_designator
}

function isHighOrbitSatellite(satellite: MapSatellitePoint): boolean {
  const { perigee_km: perigee, apogee_km: apogee } = satellite.orbit
  return (
    satellite.orbit_type === 'geo' ||
    (perigee !== null && perigee >= HIGH_ORBIT_ALTITUDE_KM) ||
    (apogee !== null && apogee >= HIGH_ORBIT_ALTITUDE_KM) ||
    (satellite.group_name?.includes('高轨') ?? false)
  )
}

export default App
