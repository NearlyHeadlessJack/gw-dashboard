<div align="center">

# GW Dashboard

  <img src="docs/assets/logo.svg" width="560" alt="GW Dashboard logo" />

  [![PyPI Version](https://img.shields.io/pypi/v/gw-dashboard?cacheSeconds=3600)](https://pypi.org/project/gw-dashboard/)
  [![Python Version](https://img.shields.io/pypi/pyversions/gw-dashboard?cacheSeconds=3600)](https://pypi.org/project/gw-dashboard/)
  [![License](https://img.shields.io/pypi/l/gw-dashboard?cacheSeconds=3600)](https://www.gnu.org/licenses/gpl-3.0.en.html)
  [![Publish](https://github.com/NearlyHeadlessJack/gw-dashboard/actions/workflows/publish.yml/badge.svg?branch=main)](https://github.com/NearlyHeadlessJack/gw-dashboard/actions/workflows/publish.yml)

**星网（GW）卫星星座数据仪表盘**

基于互联网公开信息，自动化收集星网/国网星座的运行与发射数据，提供可视化仪表盘和交互式地图展示。

<img src="docs/assets/example.gif" width="600" alt="GW Dashboard 示例" />

</div>

## 功能特性

- **数据仪表盘** — 卫星与发射统计总览、制造商/火箭分布图表
- **交互式地图** — 卫星实时位置与轨迹展示，支持 LEO 覆盖范围可视化
- **轨道追踪** — 前端基于 SGP4/TLE 实时解算卫星轨道，近地点/远地点历史图表
- **自动更新** — 后台守护进程定期爬取最新 TLE 数据，无需手动干预
- **多数据库支持** — SQLite / MySQL / PostgreSQL 三种后端可选


## 快速开始

### 安装

```bash
# 从 PyPI 安装（推荐）
pip install gw-dashboard

# 或从源码安装
git clone https://github.com/NearlyHeadlessJack/gw-dashboard.git
cd gw-dashboard
uv sync
```

> 遇到安装问题？参见 [安装指南](docs/install-guide.md)，涵盖 Windows、Linux（虚拟环境 / pipx / uv）和 macOS 的详细说明。

也可以使用 Docker 部署，镜像托管在 GitHub Container Registry；详细步骤见 [安装指南的 Docker 部署章节](docs/install-guide.md#docker-部署)。

### 运行

```bash
# PyPI 安装后直接运行
gw-dashboard

# 从源码运行
uv run -m gw

# 开发模式（启动前自动构建前端，需要 Node.js）
uv run -m gw -d

# 只读模式（禁止通过页面或 API 修改数据有效期）
gw-dashboard -r
```

首次运行时，如果数据库不存在，程序会自动爬取数据并初始化，然后启动 Web 服务。控制台会打印访问 URL。

### 命令行参数

| 参数 | 说明 |
|------|------|
| `-c`, `--config <path>` | 指定 YAML 配置文件的路径 |
| `-d`, `--build-frontend` | 启动前执行 `npm run build` 构建前端（需 Node.js） |
| `-r`, `--readonly` | 只读模式，禁止通过页面或 API 修改数据有效期 |

### 配置文件

默认无需配置文件即可运行（使用 SQLite，数据库路径 `~/.gwtracking/database.db`）。

如需自定义，复制示例配置并指定文件：

```bash
cp config.example.yaml config.yaml
gw-dashboard -c config.yaml
```

**加载优先级**（从低到高）：
1. 代码内默认值
2. YAML 配置文件（通过 `-c` 指定）
3. 环境变量（`GW_*` 前缀，覆盖 YAML 中的同名配置）

`-d` / `-r` 为纯命令行参数，不受 YAML 或环境变量影响。

#### 完整配置项参考

```yaml
# 数据库设置
database:
  type: sqlite3                                   # sqlite3 / mysql / postgresql
  # 方式一：直接写路径或 SQLAlchemy URL
  connection: database/gw.sqlite3
  # 方式二：拆分填写连接信息（用于 MySQL / PostgreSQL）
  # connection:
  #   driver: "mysql+pymysql"
  #   host: "127.0.0.1"
  #   port: 3306
  #   username: "root"
  #   password: "secret"
  #   database: "gw_dashboard"

# 后端服务
backend:
  host: 0.0.0.0                                   # 监听地址
  port: 8000                                      # 监听端口
  reload: false                                   # 热重载（当前不支持，设为 true 会报错）
  cors_origins:                                   # CORS 允许的来源
    - http://localhost:5173
  cache_ttl_seconds: 30                           # API 缓存时间（秒）

# 前端服务
frontend:
  origin: http://localhost:5173                   # 开发时代理的前端 dev server
  dist_dir: gw/web/static                         # 前端静态文件目录

# 守护进程（定时爬取数据）
daemon:
  update_check_interval_seconds: 3600             # 更新检查间隔（秒）
  data_valid_duration_seconds: 86400              # 数据有效时长（秒），超时后自动爬取
  satellite_record_limit: 1000                    # 卫星记录数上限

# 爬虫
scraper:
  huiji_url: null                                 # 卫星百科 URL（默认内置地址）
  celestrak_url: null                             # CelesTrak URL（默认内置地址）
  network_timeout_seconds: 30                     # 网络请求超时（秒）
```

#### 环境变量参考

所有环境变量以 `GW_` 为前缀，可替代或覆盖 YAML 配置。配置键名用双下划线 `__` 分隔嵌套层级（如 `GW_DATABASE__TYPE`），也可以直接用单下划线分隔的扁平形式（如 `GW_DATABASE_TYPE`）。

**数据库**

| 环境变量 | 说明 |
|----------|------|
| `GW_DATABASE_TYPE` | 数据库类型：`sqlite3` / `mysql` / `postgresql` |
| `GW_DATABASE_PATH` | SQLite 数据库文件路径 |
| `GW_DATABASE_CONNECTION` | 完整的 SQLAlchemy 连接 URL（设置后忽略下方拆分项） |
| `GW_DATABASE_DRIVER` | 数据库驱动（如 `mysql+pymysql`） |
| `GW_DATABASE_HOST` | 数据库主机地址 |
| `GW_DATABASE_PORT` | 数据库端口 |
| `GW_DATABASE_USER` / `GW_DATABASE_USERNAME` | 数据库用户名 |
| `GW_DATABASE_PASSWORD` | 数据库密码 |
| `GW_DATABASE_NAME` / `GW_DATABASE_DB` | 数据库名称 |

**后端**

| 环境变量 | 说明 |
|----------|------|
| `GW_BACKEND_HOST` | 监听地址（默认 `0.0.0.0`） |
| `GW_BACKEND_PORT` | 监听端口（默认 `8000`） |
| `GW_BACKEND_RELOAD` | 是否热重载（默认 `false`，设为 `true` 会报错） |
| `GW_BACKEND_CORS_ORIGINS` | CORS 来源，逗号分隔（如 `http://a.com,http://b.com`） |
| `GW_BACKEND_CACHE_TTL_SECONDS` | API 缓存时间（默认 `30`） |

**前端**

| 环境变量 | 说明 |
|----------|------|
| `GW_FRONTEND_ORIGIN` | 前端 dev server 地址（默认 `http://localhost:5173`） |
| `GW_FRONTEND_DIST_DIR` | 前端静态文件目录（默认 `gw/web/static`） |

**守护进程**

| 环境变量 | 说明 |
|----------|------|
| `GW_DAEMON_UPDATE_CHECK_INTERVAL_SECONDS` | 更新检查间隔（默认 `3600`） |
| `GW_DAEMON_DATA_VALID_DURATION_SECONDS` | 数据有效时长（默认 `86400`） |
| `GW_DAEMON_SATELLITE_RECORD_LIMIT` | 卫星记录数上限（默认 `1000`） |

**爬虫**

| 环境变量 | 说明 |
|----------|------|
| `GW_SCRAPER_HUIJI_URL` | 卫星百科 URL（默认内置地址） |
| `GW_SCRAPER_CELESTRAK_URL` | CelesTrak URL（默认内置地址） |
| `GW_SCRAPER_NETWORK_TIMEOUT_SECONDS` | 网络请求超时（默认 `30`） |

## 项目结构

```
gw-dashboard/
├── gw/                  # 后端源码
│   ├── __main__.py      # 入口程序
│   ├── config.py        # 配置加载
│   ├── startup.py       # 启动初始化
│   ├── scraper/         # 数据爬取
│   ├── database/        # 数据库操作
│   ├── web/             # API 与静态资源
│   ├── daemon/          # 守护进程（定时更新）
│   ├── orbit/           # 轨道计算
│   └── utils/           # 工具函数
├── frontend/            # 前端源码
│   └── src/
│       ├── App.tsx      # 主应用
│       ├── api.ts       # API 调用
│       ├── orbit.ts     # 轨道解算
│       └── types.ts     # 类型定义
├── tests/               # 后端测试
├── database/            # 数据库存储目录
└── pyproject.toml       # 项目配置
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 19 · TypeScript · Vite 8 · Leaflet · satellite.js |
| 后端 | Python ≥3.12 · FastAPI · SQLAlchemy · SGP4 |
| 包管理 | uv (后端) / npm (前端) |
| 测试 | pytest / ESLint |

## 开发

### 后端

```bash
# 安装依赖
uv sync

# 运行测试
uv run pytest

# 代码检查
uv run ruff check .
```

### 前端

```bash
cd frontend

# 安装依赖
npm install

# 开发服务器
npm run dev

# 构建
npm run build

# 代码检查
npm run lint
```

### 构建发布包

```bash
# 先构建前端
cd frontend && npm run build && cd ..

# 再构建 Python wheel
uv build
```

## 数据来源

所有数据均来自公开信息（CelesTrak、卫星百科 等），仅供学习参考。  

> Code with Codex (GPT5.5) & Claude Code (GLM5.1 / DeepSeek-V4-Pro)

## 许可证

[GPL-3.0](LICENSE)
