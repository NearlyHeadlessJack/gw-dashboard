# gw-dashboard
StarNet Satellite On-Orbit Operation Status Collection and Analysis System. 中国星网卫星在轨运行状态开源收集和分析系统。

## 本地运行

后端：

```bash
uv sync
mkdir -p database
uv run python -m gw.web -c config.example.yaml
```

前端：

```bash
cd frontend
npm install
VITE_AMAP_KEY=你的高德Web端Key npm run dev
```

开发模式下 Vite 会把 `/api` 代理到 `http://127.0.0.1:8000`。如果高德账号启用了安全密钥，同时设置 `VITE_AMAP_SECURITY_JS_CODE`。

## 验证

```bash
uv run pytest
cd frontend && npm run lint && npm run build
```
