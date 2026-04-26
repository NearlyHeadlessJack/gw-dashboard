import { useEffect, useMemo, useRef, useState, type PointerEvent } from 'react'
import {
  BrowserRouter,
  Navigate,
  NavLink,
  Route,
  Routes,
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
} from 'lucide-react'
import { useApi } from './api'
import type {
  DashboardData,
  GeoPoint,
  GroupDetail,
  GroupSummary,
  HistoryPoint,
  LaunchPreview,
  MapPayload,
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

  if (loading || satellitesLoading || launchesLoading) {
    return <LoadingState label="仪表盘同步中" />
  }
  if (error || satellitesError || launchesError) {
    return <ErrorState message={error ?? satellitesError ?? launchesError ?? ''} />
  }
  if (!data || !satellites || !launches) {
    return <EmptyState label="暂无仪表盘数据" />
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
          className="span-7"
          title="最近发射卫星"
          icon={Orbit}
          meta={formatDateTime(data.summary.last_updated_at)}
        >
          <RecentSatellitesTable satellites={satellites} scrollable />
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
  const [groupIntl, setGroupIntl] = useState('')
  const [satelliteIntl, setSatelliteIntl] = useState('')
  const selectedGroupIntl = groupIntl || groups?.[0]?.intl_designator || ''

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
        selectedSatellite={satelliteIntl}
        satellites={detail?.satellites ?? []}
        onGroupChange={(value) => {
          setGroupIntl(value)
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
  const [refreshKey, setRefreshKey] = useState(0)
  const { data, loading, error } = useApi<MapPayload>(
    '/api/map/groups',
    refreshKey,
  )

  useEffect(() => {
    const id = setInterval(() => setRefreshKey((value) => value + 1), 30_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="map-page">
      <SatelliteMap payload={data} />
      <div className="map-hud">
        <div className="map-hud-main">
          <span className="hud-label">GROUP TRACKS</span>
          <strong>{formatNumber(data?.groups.length ?? 0)}</strong>
        </div>
        <div className="hud-meta">
          <Clock size={14} />
          <span>{formatTime(data?.generated_at)}</span>
        </div>
        <button
          className="icon-button"
          type="button"
          onClick={() => setRefreshKey((value) => value + 1)}
          title="刷新轨迹"
        >
          <RefreshCw size={16} />
        </button>
      </div>
      {loading && <div className="map-state">轨迹同步中</div>}
      {error && <div className="map-state error">{error}</div>}
    </div>
  )
}

function SatelliteMap({ payload }: { payload: MapPayload | null }) {
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
      maxZoom: 10,
      worldCopyJump: true,
      zoomControl: false,
    })

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
    const map = mapRef.current
    const overlayLayer = overlayLayerRef.current
    if (!map || !overlayLayer || !payload) return

    overlayLayer.clearLayers()
    const bounds = L.latLngBounds([])

    let leoIndex = 0
    payload.groups.forEach((group) => {
      const color = LEO_TRACK_COLORS[leoIndex++ % LEO_TRACK_COLORS.length]
      splitTrackByDateline(group.track).forEach((segment) => {
        L.polyline(segment, {
          color,
          opacity: 0.72,
          weight: 1.8,
          lineJoin: 'round',
        }).addTo(overlayLayer)
      })

      const marker = L.circleMarker(pointToLatLng(group.position), {
        radius: 4,
        color: '#ffffff',
        weight: 1.3,
        fillColor: color,
        fillOpacity: 0.96,
      }).addTo(overlayLayer)
      marker.bindTooltip(
        `${group.name ?? group.intl_designator}<br>${mapTooltipIdentifier(group)}<br>${formatKm(group.orbit.perigee_km)} × ${formatKm(group.orbit.apogee_km)}`,
        { direction: 'top', offset: [0, -8] },
      )
      bounds.extend(pointToLatLng(group.position))
    })

    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [80, 80], maxZoom: 3 })
    } else {
      map.setView([25, 105], 2)
    }
  }, [payload])

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
}: {
  satellites: SatellitePreview[]
  scrollable?: boolean
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
              <td className="mono">{satellite.intl_designator}</td>
              <td>{satellite.group_name ?? '-'}</td>
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
            <strong>{launch.name ?? launch.intl_designator}</strong>
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
}: {
  title: string
  icon: IconComponent
  children: React.ReactNode
  className?: string
  dense?: boolean
  meta?: string
}) {
  return (
    <section className={`panel ${dense ? 'dense' : ''} ${className}`}>
      <header className="panel-header">
        <div>
          <Icon size={17} />
          <h2>{title}</h2>
        </div>
        {meta && <span>{meta}</span>}
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
  return (
    <BrowserRouter>
      <div className="app">
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
  if (!value) return '--:--:--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '--:--:--'
  return date.toISOString().slice(11, 19)
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

function orbitSentence(orbit: OrbitSummary): string {
  return `${formatDegree(orbit.inclination_deg)} / ${formatKm(
    orbit.perigee_km,
  )} - ${formatKm(orbit.apogee_km)}`
}

function mapTooltipIdentifier(group: { intl_designator: string; orbit_type: string }): string {
  return group.orbit_type === 'geo'
    ? `${group.intl_designator} · GEO`
    : group.intl_designator
}

export default App
