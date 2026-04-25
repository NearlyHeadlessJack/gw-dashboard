import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, NavLink } from 'react-router-dom'
import './App.css'

function useClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return now
}

const DASHBOARD_MENU = [
  { path: '/dashboard', label: '仪表盘', icon: '◈' },
  { path: '/dashboard/orbits', label: '当前轨道', icon: '◎' },
  { path: '/dashboard/launches', label: '发射统计', icon: '△' },
  { path: '/dashboard/history', label: '历史轨道', icon: '∰' },
]

function DashboardLayout() {
  return (
    <div className="dashboard-layout">
      <aside className="sidebar">
        <div className="sidebar-scanlines" />
        <nav className="sidebar-nav">
          {DASHBOARD_MENU.map((item, index) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/dashboard'}
              className={({ isActive }) =>
                `menu-item${isActive ? ' active' : ''}`
              }
              style={{ animationDelay: `${index * 60}ms` }}
            >
              <span className="menu-icon">{item.icon}</span>
              <span className="menu-label">{item.label}</span>
              <span className="menu-indicator" />
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="status-dot" />
          <span className="status-text">ONLINE</span>
        </div>
      </aside>
      <main className="dashboard-content">
        <div className="content-grid-overlay" />
        <Routes>
          <Route index element={<div />} />
          <Route path="orbits" element={<div />} />
          <Route path="launches" element={<div />} />
          <Route path="history" element={<div />} />
        </Routes>
      </main>
    </div>
  )
}

function MapPage() {
  return (
    <div className="map-page">
      <div className="map-grid-overlay" />
    </div>
  )
}

function App() {
  const now = useClock()
  return (
    <BrowserRouter>
      <div className="app">
        <header className="top-nav">
          <div className="nav-brand">
            <span className="brand-icon">◉</span>
            <span className="brand-text">星网</span>
            <span className="brand-sub">GW DASHBOARD</span>
          </div>
          <nav className="nav-tabs">
            <NavLink
              to="/dashboard"
              className={({ isActive }) =>
                `tab${isActive ? ' active' : ''}`
              }
            >
              <span className="tab-icon">▦</span>
              仪表盘
            </NavLink>
            <NavLink
              to="/map"
              className={({ isActive }) =>
                `tab${isActive ? ' active' : ''}`
              }
            >
              <span className="tab-icon">◎</span>
              地图
            </NavLink>
          </nav>
          <div className="nav-time">
            <span className="time-label">UTC</span>
            <span className="time-value">
              {now.toISOString().slice(11, 19)}
            </span>
          </div>
          <div className="nav-time">
            <span className="time-label">BJT</span>
            <span className="time-value">
              {now.toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })}
            </span>
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

export default App