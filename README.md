# Agentic BI — Olist 多表电商运营分析与决策智能系统

面向业务人员的自然语言 BI：**中心化多智能体（ReAct + function-calling + Plan-and-Execute + Reflexion）** + **MySQL 物理预聚合加速** + **Vite/ECharts 三栏前端**，覆盖描述性、诊断性、预测性、规范性四层分析，仓库数据与运行时数据在数据库权限层物理隔离。

## 1. 架构

```text
data_layer/   离线工具：建库 → 版本迁移 → 清洗装载9表 → 构建预聚合 → 校验/benchmark，跑完即退出
backend/      FastAPI + 中心 supervisor Agent + 专家子 Agent（ReAct / Plan-and-Execute / 工具调用）
frontend/     Vite + ECharts，左历史栏 / 中对话 / 右图表面板
```

### 1.1 两个物理隔离的数据库

| 库 | 内容 | 账号 |
| --- | --- | --- |
| `olist_bi` | 数据仓库：9 基础表 + `fact_order_items` 事实宽表 + **11 张可刷新物理预聚合表 `mv_*`** + `mv_refresh_log` | Agent 运行时用只读 `olist_ro`（DB 层兜底防写） |
| `agentic_app` | 运行时业务：`conversations` / `messages`（含每条消息的图表与 SQL 产物）/ `query_route_log` 审计 | `olist_etl` 读写 |

只读账号在 DB 权限层即**无法访问** `agentic_app`、**无法写** `olist_bi`，从机制上避免历史结果污染当前问题。

### 1.2 多智能体

- **中心 supervisor**（`orchestration/supervisor.py`）：ReAct + function-calling，按需调用专家工具；单个数据问题原样交给数据 Agent，不按州/品类拆分。
- **数据分析子 Agent**（`agents/data_agent.py`）：**Plan-and-Execute + Reflect + Replan**。先产出显式计划与口径，再 ReAct 执行（`list_views` / `describe_view` / `run_sql`，SQL 报错自我修正），反思核对 Top N 个数、时间维度、加权口径与题型，不达标则重规划（有界），最后在源头甄别最终依据的查询。**不使用黄金/模板 SQL**，全部 LLM 实时编写。
- **专家子 Agent**：预测（`forecast_agent`，对数尺度阻尼 Holt + 90% 区间）、What-if（`whatif_agent`，反事实模拟）、异常检测（`anomaly_agent`，环比/z-score）、配送诊断（`diagnose_agent`，haversine 地理距离下钻）、评论 NLP（`review_agent`，葡语情感 + 分色词云）。
- **可视化 Agent**（`agents/viz_agent.py`）：LLM 按数据特征决定哪些数据出图、用何类型、如何编码、起何标题；绘图工具 `viz/charts.py` 确定性渲染并校验兜底。
- **元/记忆 Agent**（`meta_agent.py`）：处理与数据无关的消息（寒暄、历史回顾）。
- **长短期记忆**：短期=近期消息注入上下文，长期=会话摘要持久化于 `agentic_app`，跨重启可恢复。
- **模型可切换**：`llm/client.py` 抽象，前端顶栏随时切 `cloud`(DeepSeek/Qwen) ↔ 本地 `ollama`。
- **提示词外置**：Agent 的 system prompt 在 `backend/llm/prompts/*.txt`，按 `__file__` 相对路径加载，便于维护。

### 1.3 可视化与前端

- 图表类型按数据形态自动选型：折线 / 分组折线 / 柱状 / 饼图 / 散点-气泡 / 热力图 / **地理气泡图** / 预测带区间 / What-if 前后对比 / 配送诊断散点 / 异常幅度 / 分色词云。
- 左历史会话（新建/切换/改名/删除）；中对话（标题可改、模型选择、行内 Agent 状态、可滚动建议）；右图表面板（**上=图表，下=本次 SQL / 命中表 / 耗时**）。
- 每条 AI 消息可复制、可“查看”回看那一轮的图表与 SQL（历史从 DB 重放）；图表可放大、下载 PNG。

## 2. 运行环境与依赖

- Python 3.10+，Node 18+，MySQL 8.x（推荐 Docker），DeepSeek API Key（或本地 Ollama）。

## 3. 运行

### 阶段 A：离线建库（仅首次 / 数据或口径变更时）

1. 启动 MySQL：

```bash
docker compose up -d        # 见根目录 docker-compose.yml；库与账号由 init_db 自动创建
```

2. 准备数据：从 [Kaggle Olist 数据集](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) 下载 9 个 CSV 放入 `data_layer/data/raw/`。

3. 建库与预聚合：

```bash
cd data_layer
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # 默认 
python -m utils.init_db            # 建库          
python -m scripts.benchmark_preagg # 预聚合性能对比
python -m pytest tests/ -q         # 数据质量校验
```

### 阶段 B：在线运行

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # 填 CLOUD_API_KEY；LLM_PROVIDER=cloud|ollama
python -m uvicorn app:app --reload --port 8000   # 启动时自动 bootstrap agentic_app

cd ../frontend
npm install
npm run dev                        # http://localhost:5173
```

## 4. API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/chat` | SSE：行内状态 + 最终结论 + 图表 + 本次查询(SQL/命中表/耗时) |
| GET/POST | `/api/conversations` | 会话列表 / 新建 |
| GET | `/api/conversations/{id}/messages` | 历史消息（含每条产物 meta） |
| PATCH/DELETE | `/api/conversations/{id}` | 改名 / 删除 |
| GET | `/api/models` | 可用 LLM（云/本地） |
| GET | `/api/route_stats` | 视图命中率 / 平均耗时 |
| GET | `/api/refresh_log` | 预聚合刷新历史 |

## 5. 目录结构

```text
AgenticBI_Final_Olist1/
├── data_layer/                # 离线：utils(init_db/migrate/load/clean/refresh_aggregations) + scripts/benchmark + sql + migrations
├── backend/
│   ├── app.py                 # FastAPI 入口 + SSE
│   ├── orchestration/         # supervisor + LangGraph 图编排
│   ├── agents/                # data/forecast/whatif/anomaly/diagnose/review/viz/meta + planner + reflection
│   ├── viz/charts.py          # ECharts 渲染（确定性，含地理气泡/词云等）
│   ├── datastore/             # 两库访问、数据字典、schema 提示、审计
│   ├── models/                # 预测、评论 NLP
│   ├── llm/                   # 云/本地客户端 + prompts/*.txt
│   └── core/                  # 配置、SQL 安全校验
├── frontend/                  # Vite + ECharts 三栏前端
├── docs/                      # 报告、演示脚本、模板、排查、验证问题、证据截图
├── docker-compose.yml
└── README.md
```

## 6. 验证示例

- 描述：`2017 年哪个州的销售额最高？交付准时率是多少？哪种支付方式最受欢迎？`
- 地理：`在地图上展示各州销售额的地理分布。`
- 诊断：`为什么有些州平均配送时长显著高于全国均值？`
- 预测：`根据历史趋势预测未来 6 周销售额，并给出趋势解读。`
- What-if：`如果下架 Top20 高差评卖家，平台评分会怎样？`
- 异常：`扫描最近各州订单量和差评率是否有异常。`
- 记忆：`我上一个问题问的是什么？`

完整验证问题见 `docs/appendix_validation_queries.md`，演示流程见 `docs/demo_script.md`，项目报告见 `docs/project_report.md`。

## 7. 与评分项对照

- **数据预处理与多表查询准确性**：9 表清洗装载、`fact_order_items` 事实宽表、跨表 JOIN 与回退。
- **预聚合视图设计与性能优化**：11 张带索引物理预聚合表 + 一键刷新 + `benchmark_preagg`。
- **Agentic BI 多智能体协作**：supervisor + 数据/预测/What-if/异常/诊断/评论/可视化/元 多 Agent，ReAct + Reflexion + Plan-and-Execute。
- **分析完整度**：描述 / 诊断 / 预测 / 规范四层全覆盖。
- **可视化与交互**：12 类图表 + LLM 决策选型 + 三栏交互界面。
- **报告与演示**：`docs/` 提供报告、模板、演示脚本与证据目录。

## 8. 说明

沿用原始 Olist 列名（`year_month` 等）以复用稳定的预聚合 SQL；数据字典见 `backend/datastore/data_dictionary.py`。数据集与结论仅用于课程教学与研究演示。
