# 常见问题与排查

## 数据未就绪

确认 `data_layer/data/raw/` 中包含 9 个 Olist CSV，然后在 `data_layer/` 下一键编排：

```bash
cd data_layer
python -m utils.init_db
```

该命令按序完成：建库 → 版本迁移（账号/表/索引/日志）→ 清洗装载 9 表 → 刷新预聚合 + 自校验。
仅刷新预聚合可单独运行 `python -m utils.refresh_aggregations`。

## MySQL 连接失败

检查 Docker 容器、端口、账号密码与库名。两套账号：`olist_etl`（读写）、`olist_ro`（只读，后端 Agent 运行时使用）。
- 启动数据库：`docker compose up -d`，查看 `docker ps`。
- 账号与库由 `init_db` 自动创建，无需手动建。

## 云端 LLM 报 SSL / Connection error

多为本地代理（如 Clash）把对国内 API（DeepSeek）的请求绕到外区出口导致 TLS 中断。
- 默认已让云端**绕过系统代理直连**（`llm/client.py`），通常无需处理。
- 若确需经代理（例如改用 OpenAI），在 `backend/.env` 设 `CLOUD_USE_PROXY=true`。
- 本地 Ollama 始终绕过代理直连 `127.0.0.1`。

## 本地 Ollama 不可用

确认 `ollama serve` 已启动且 `OLLAMA_BASE_URL` 正确（默认 `http://127.0.0.1:11434/v1`）。
前端顶栏可在 `cloud` 与 `ollama` 间切换；未连接的 provider 会标注「未连接」。

## 地理热力图/气泡图不出现

地理图依赖含经纬度的 `mv_state_geo_sales`。提问需包含「地图 / 地理分布 / 热力图 / 气泡图」等词，数据 Agent 才会命中该视图。
普通「各州销售额」会命中无坐标的 `mv_state_sales`，只出柱状图。

## 图表缺失或不相关

可视化 Agent 按本轮结果字段决定是否出图：与问题无关、中间过程、单值或无可绘字段的数据集会被跳过。
若数据 Agent 未查出含所需维度的结果（如趋势缺时间列），反思会要求重查；仍不足时如实说明数据边界。

## 前端连不上后端

确认后端在 `127.0.0.1:8000` 运行，前端 `vite` 代理或 `fetch` 指向该地址；用 `localhost` 而非 `::1`。

## 性能/证据材料

```bash
cd data_layer
python -m scripts.benchmark_preagg
```

生成 `data/processed/benchmark_report.json` 与 `benchmark_report.png`，将截图补入 `docs/evidence/`。
