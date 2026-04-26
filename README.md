# gw-dashboard
StarNet Satellite On-Orbit Operation Status Collection and Analysis System. 中国星网卫星在轨运行状态开源收集和分析系统。

## 本地运行

运行时只需要启动后端进程；后端会同时托管 Python 包内置的前端静态页面。通过 PyPI 安装时不需要 Node.js。

```bash
pip install gw-dashboard
gw-dashboard
```

也可以使用模块入口：

```bash
python -m gw
```

从源码运行已构建版本时：

```bash
uv sync
uv run -m gw
```

修改前端后需要重新构建静态资源：

```bash
cd frontend
npm install
npm run build
cd ..
uv run -m gw
```

也可以用 `-d` 在启动前自动执行一次前端构建：

```bash
uv run -m gw -d
```

`-d` / `--build-frontend` 会在启动后端前运行 `npm run build`，需要本机有 Node.js/npm，且当前安装方式能找到源码里的 `frontend` 目录。`npm run build` 会把前端产物写入 `gw/web/static`，这是发布到 PyPI 的 wheel 中携带的静态资源目录。只有修改或重新构建前端时才需要 Node.js；普通用户安装运行不需要。

默认不需要任何配置文件；后端会使用 SQLite，并自动创建 `~/.gwtracking/database.db`。启动后控制台会打印前端入口 URL，可直接打开 `http://127.0.0.1:8000` 访问页面，关闭后端进程后前端也会停止服务。地图页使用公共高德标准瓦片，不需要配置地图 Key。

后端启动后，控制台会持续输出运行状态，包括：

- Web 服务监听地址、前端构建目录
- 数据库初始化和元信息状态
- daemon 启动、检查间隔、每轮数据过期检查结果
- 灰机 wiki 爬虫开始/结束、解析到的发射组数量
- Celestrak TLE 获取进度、每组有效/失效卫星统计
- 本轮数据更新汇总和异常堆栈

前端开发时可以单独启动 Vite 热更新服务：

```bash
cd frontend
npm run dev
```

开发模式下 Vite 会把 `/api` 代理到 `http://127.0.0.1:8000`。

## 验证

```bash
uv run pytest
cd frontend && npm run lint && npm run build
uv build
```
