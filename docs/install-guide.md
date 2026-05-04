# 安装指南

本软件需要 Python ≥ 3.12。部分 Linux 发行版禁止直接使用系统 Python 安装包（PEP 668），需要通过虚拟环境或第三方工具安装。

以下按平台介绍安装方法。

---

## Windows

1. 打开 PowerShell（在开始菜单搜索"PowerShell"或右键开始菜单选择"终端"）
2. 确认 Python 版本：

   ```powershell
   python --version
   ```

   如果版本低于 3.12，从 [python.org](https://www.python.org/downloads/) 下载安装，安装时勾选"Add Python to PATH"。

3. 安装并运行：

   ```powershell
   pip install gw-dashboard
   gw-dashboard
   ```

---

## Linux

Linux 上有三种安装方式，选择一种即可。

### 方式一：虚拟环境（推荐，不需要额外工具）

适用于所有 Linux 发行版，无需安装 pipx 或 uv。

```bash
# 创建虚拟环境
python3 -m venv ~/.venvs/gw-dashboard

# 激活虚拟环境
source ~/.venvs/gw-dashboard/bin/activate

# 安装
pip install gw-dashboard

# 运行
gw-dashboard
```

后续每次使用前需要先激活虚拟环境：

```bash
source ~/.venvs/gw-dashboard/bin/activate
gw-dashboard
```

也可以不激活直接运行：

```bash
~/.venvs/gw-dashboard/bin/gw-dashboard
```

### 方式二：使用 pipx

pipx 会自动为每个工具创建独立虚拟环境，适合安装命令行工具。

#### 安装 pipx

**Ubuntu / Debian：**

```bash
sudo apt update
sudo apt install pipx
pipx ensurepath
```

**Fedora：**

```bash
sudo dnf install pipx
pipx ensurepath
```

**Arch Linux：**

```bash
sudo pacman -S python-pipx
pipx ensurepath
```

**其他发行版（或上述方式不可用）：**

```bash
python3 -m pip install --user pipx
pipx ensurepath
```

> `pipx ensurepath` 执行后需要重新打开终端，或执行 `source ~/.bashrc`（zsh 用户执行 `source ~/.zshrc`）。

#### 安装并运行

```bash
pipx install gw-dashboard
gw-dashboard
```

更新：

```bash
pipx upgrade gw-dashboard
```

卸载：

```bash
pipx uninstall gw-dashboard
```

### 方式三：使用 uv

uv 是极速的 Python 包管理器，适合同时管理开发环境。

#### 安装 uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

> 安装完成后需要重新打开终端，或执行 `source ~/.bashrc`（zsh 用户执行 `source ~/.zshrc`）。

**macOS (Homebrew)：**

```bash
brew install uv
```

#### 安装并运行

```bash
uv tool install gw-dashboard
gw-dashboard
```

更新：

```bash
uv tool upgrade gw-dashboard
```

卸载：

```bash
uv tool uninstall gw-dashboard
```

---

## macOS

macOS 自带或 Homebrew 安装的 Python 通常没有 PEP 668 限制，可以直接用 pip 安装。如遇问题，参考 Linux 的方式一或方式三。

```bash
# 直接安装
pip3 install gw-dashboard
gw-dashboard
```

或使用 Homebrew 安装 uv：

```bash
brew install uv
uv tool install gw-dashboard
gw-dashboard
```

---

## 常见问题

### `externally-managed-environment` 错误

完整错误信息类似：

```
error: externally-managed-environment
× This environment is externally managed
```

这是 PEP 668 的限制，部分 Linux 发行版（如 Ubuntu 23.04+、Debian 12+、Fedora 38+）禁止直接向系统 Python 安装包。解决方法：

- **方法 A**：使用上方"方式一"创建虚拟环境
- **方法 B**：使用 pipx 或 uv 安装（见"方式二"和"方式三"）
- **方法 C（不推荐）**：强制安装，可能破坏系统 Python 环境

  ```bash
  pip install --break-system-packages gw-dashboard
  ```

### `python3 -m venv` 报错

部分精简安装的系统缺少 `venv` 模块：

**Ubuntu / Debian：**

```bash
sudo apt install python3-venv
```

**Fedora：**

```bash
sudo dnf install python3-venv
```

### Windows 下 `python` 命令不存在

在 Microsoft Store 安装的 Python 可能只有 `python3` 或 `python3.12` 命令。可以：

- 从 [python.org](https://www.python.org/downloads/) 重新安装，勾选"Add Python to PATH"
- 或使用 `python3 -m pip install gw-dashboard` 代替

### 安装后 `gw-dashboard` 命令找不到

- 检查 Python 的 `bin` 目录是否在 `PATH` 中
- 虚拟环境方式：确认已 `source ~/.venvs/gw-dashboard/bin/activate`
- pipx/uv 方式：确认已执行 `pipx ensurepath` 或重新打开终端

---

## 配置

默认无需任何配置即可运行（SQLite 数据库，路径 `~/.gwtracking/database.db`）。

### 命令行参数

| 参数 | 说明 |
|------|------|
| `-c`, `--config <path>` | 指定 YAML 配置文件的路径 |
| `-d`, `--build-frontend` | 启动前执行 `npm run build` 构建前端（需 Node.js） |
| `-r`, `--readonly` | 只读模式，禁止通过页面或 API 修改数据有效期 |

### 配置文件

如需自定义，复制项目示例配置并指定文件：

```bash
cp config.example.yaml config.yaml
gw-dashboard -c config.yaml
```

`config.example.yaml` 在源码仓库根目录中；PyPI 安装后可手动创建 YAML 文件。完整配置项参考：

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

**加载优先级**（从低到高）：
1. 代码内默认值
2. YAML 配置文件（通过 `-c` 指定）
3. 环境变量（`GW_*` 前缀，覆盖 YAML 中的同名配置）

`-d` / `-r` 为纯命令行参数，不受 YAML 或环境变量影响。

### 环境变量参考

所有环境变量以 `GW_` 为前缀，可以替代或覆盖 YAML 配置。

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
| `GW_BACKEND_CORS_ORIGINS` | CORS 来源，逗号分隔 |
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

---

## Docker 部署

### 基本使用

官方镜像发布在 GitHub Container Registry：

```bash
docker pull ghcr.io/nearlyheadlessjack/gw-dashboard:latest
docker run -p 8000:8000 ghcr.io/nearlyheadlessjack/gw-dashboard:latest
```

启动后访问 `http://localhost:8000` 即可。

如果需要只读模式（禁止通过页面或 API 修改数据有效期），在镜像名后追加 `-r`：

```bash
docker run -p 8000:8000 ghcr.io/nearlyheadlessjack/gw-dashboard:latest -r
```

Docker 部署配置方式同上方的[环境变量参考](#环境变量参考)，所有 `GW_*` 环境变量均可用 `-e` 传入。

### 数据库配置

#### SQLite（默认）

```bash
docker run -p 8000:8000 \
  -v gw-data:/root/.gwtracking \
  ghcr.io/nearlyheadlessjack/gw-dashboard:latest
```

```bash
# 自定义路径
docker run -p 8000:8000 \
  -e GW_DATABASE_TYPE=sqlite3 \
  -e GW_DATABASE_PATH=/data/gw.sqlite3 \
  -v gw-data:/data \
  ghcr.io/nearlyheadlessjack/gw-dashboard:latest
```

#### MySQL

```bash
docker run -p 8000:8000 \
  -e GW_DATABASE_TYPE=mysql \
  -e GW_DATABASE_CONNECTION='mysql+pymysql://root:password@db:3306/gw_dashboard' \
  ghcr.io/nearlyheadlessjack/gw-dashboard:latest
```

#### PostgreSQL

```bash
docker run -p 8000:8000 \
  -e GW_DATABASE_TYPE=pgsql \
  -e GW_DATABASE_CONNECTION='postgresql+psycopg://postgres:password@db:5432/gw_dashboard' \
  ghcr.io/nearlyheadlessjack/gw-dashboard:latest
```

也可以拆开传连接参数（MySQL 和 PostgreSQL 通用）：

```bash
docker run -p 8000:8000 \
  -e GW_DATABASE_TYPE=mysql \
  -e GW_DATABASE_HOST=db \
  -e GW_DATABASE_PORT=3306 \
  -e GW_DATABASE_USER=root \
  -e GW_DATABASE_PASSWORD=secret \
  -e GW_DATABASE_NAME=gw_dashboard \
  ghcr.io/nearlyheadlessjack/gw-dashboard:latest
```

### Docker Compose 示例

#### MySQL

```yaml
services:
  db:
    image: mysql:8
    environment:
      MYSQL_ROOT_PASSWORD: secret
      MYSQL_DATABASE: gw_dashboard
    volumes:
      - db_data:/var/lib/mysql

  app:
    image: ghcr.io/nearlyheadlessjack/gw-dashboard:latest
    ports:
      - "8000:8000"
    environment:
      GW_DATABASE_TYPE: mysql
      GW_DATABASE_CONNECTION: 'mysql+pymysql://root:secret@db:3306/gw_dashboard'
    depends_on:
      - db

volumes:
  db_data:
```

#### PostgreSQL

```yaml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_PASSWORD: secret
      POSTGRES_DB: gw_dashboard
    volumes:
      - db_data:/var/lib/postgresql/data

  app:
    image: ghcr.io/nearlyheadlessjack/gw-dashboard:latest
    ports:
      - "8000:8000"
    environment:
      GW_DATABASE_TYPE: pgsql
      GW_DATABASE_CONNECTION: 'postgresql+psycopg://postgres:secret@db:5432/gw_dashboard'
    depends_on:
      - db

volumes:
  db_data:
```
