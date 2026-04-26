# gw-dashboard
StarNet Satellite On-Orbit Operation Status Collection and Analysis System. 中国星网卫星在轨运行状态开源收集和分析系统。

## 本地运行

运行时只需要启动后端进程；后端会同时托管 `frontend/dist` 里的前端页面。

```bash
uv sync
cd frontend
npm install
npm run build
cd ..
uv run -m gw
```

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
```
