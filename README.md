# gw-dashboard
StarNet Satellite On-Orbit Operation Status Collection and Analysis System. 中国星网卫星在轨运行状态开源收集和分析系统。

## 本地运行

运行时只需要启动后端进程；后端会同时托管 `frontend/dist` 里的前端页面。

```bash
uv sync
cd frontend
npm install
VITE_AMAP_KEY=你的高德Web端Key npm run build
cd ..
mkdir -p database
uv run python -m gw.web -c config.example.yaml
```

打开 `http://127.0.0.1:8000` 即可访问前端页面，关闭后端进程后前端也会停止服务。如果高德账号启用了安全密钥，在构建前同时设置 `VITE_AMAP_SECURITY_JS_CODE`。

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
VITE_AMAP_KEY=你的高德Web端Key npm run dev
```

开发模式下 Vite 会把 `/api` 代理到 `http://127.0.0.1:8000`。

## 验证

```bash
uv run pytest
cd frontend && npm run lint && npm run build
```
