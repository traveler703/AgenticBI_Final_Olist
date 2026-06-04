# Agentic BI — Olist 多表电商运营分析与决策智能系统

基于 Olist 电商公开数据集，实现面向业务人员的自然语言分析系统。  
系统采用 **LangGraph 多智能体编排 + MySQL 物理预聚合表 + DeepSeek LLM + Streamlit 双栏仪表板**，覆盖描述性、诊断性、预测性、规范性四层分析。

## 1. 项目目标（对齐期末要求）

- 支持自然语言提问，自动执行跨表分析与 SQL 查询
- 物理预聚合层加速高频统计查询，支持“预聚合优先 + 原表回退”
- 多智能体协作完成：数据分析、可视化、决策建议与流程调度
- 输出图表、SQL、数据摘要与可执行运营建议
- 每次分析严格单轮隔离，避免历史结果污染当前问题；同一输入内的复合问题可传递必要上下文

## 2. 当前功能概览

### 2.1 物理预聚合表（已实现）

- `mv_monthly_sales`
- `mv_weekly_sales`
- `mv_state_sales`
- `mv_category_sales`
- `mv_delivery_perf`
- `mv_payment_dist`
- `mv_payment_installment_matrix`
- `mv_weight_freight_bucket`
- `mv_state_geo_sales`
- `mv_review_quality`
- `mv_seller_review_risk`

对应 SQL 定义见：`utils/sql/create_materialized_views.sql`  
刷新脚本：`python -m utils.refresh_views`

### 2.2 多智能体架构（已实现）

- `coordinator`：问题路由与流程协调
- `data_analyst`：自然语言转 SQL，优先命中 `mv_*`，失败回退原表
- `nlp_insights`：基于评论正文生成极性、主观性与主题关键词
- `visualizer`：生成标准图表输出
- `whatif_anomaly`：加分模块（What-if / 异常检测）
- `decision`：汇总分析并输出策略建议

编排入口：`agents/graph.py`（LangGraph `StateGraph`）

### 2.3 可视化能力（已实现）

当前已集成 9 类图表能力（见 `agents/visualizer.py`）。Agent 会根据本轮问题、命中数据源与结果字段动态选择相关图表，不会每轮固定返回全部 9 张：

- 月度销售趋势与独立的动态周数预测曲线（未指定时默认未来 6 周）
- 州销售额柱状图
- 支付方式柱状图
- 支付方式 × 分期数热力图
- 商品重量 × 运费散点图
- 准时交付率趋势图
- 卖家评分风险矩阵
- 州级销售额地理气泡图
- 评论文本主题关键词图

## 3. 运行环境与依赖

- Python 3.10+
- MySQL 8.x（推荐 Docker）
- DeepSeek API Key
- 依赖安装：

```bash
pip install -r requirements.txt
```

## 4. 环境变量配置

1. 复制 `.env.example` 为 `.env`
2. 填写数据库与模型参数（至少包含 MySQL 连接与 DeepSeek Key）

> 注意：`.env` 不应提交到远程仓库。

## 5. 数据准备

数据集下载地址：  
[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)

将以下 9 个 CSV 文件放入 `data/raw/`：

- `olist_orders_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_customers_dataset.csv`
- `olist_products_dataset.csv`
- `olist_sellers_dataset.csv`
- `olist_order_payments_dataset.csv`
- `olist_order_reviews_dataset.csv`
- `olist_geolocation_dataset.csv`
- `product_category_name_translation.csv`

## 6. MySQL 启动（Docker 方式）

```bash
docker compose up -d
docker ps
```

停止：

```bash
docker compose down
```

## 7. 初始化与启动步骤

在项目根目录按顺序执行：

```bash
python -m utils.db_init
python -m utils.etl
python -m utils.refresh_views
python -m utils.benchmark
python -m utils.evidence_report
streamlit run dashboard/app.py
```

也可使用入口脚本：

```bash
python app.py
```

说明：运行 `python -m utils.benchmark` 可生成性能报告与对比图。

## 8. 目录结构

```text
AgenticBI_Final_Olist/
├── agents/                    # 多智能体定义与 LangGraph 节点
├── config/                    # 配置、数据字典、Prompt
├── dashboard/                 # Streamlit 前端
├── data/raw/                  # Olist 原始 9 表 CSV
├── docs/                      # 报告模板、演示脚本、验证问题
├── models/                    # 预测、情感分析
├── utils/                     # db_init / etl / refresh_views / benchmark
├── .env.example
├── app.py
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## 9. 与期末评分项对照（自检）

- **数据预处理与多表查询准确性（20）**：已实现 9 表导入、跨表查询、物理预聚合表刷新
- **预聚合视图设计与性能优化（10）**：已实现 11 个物理预聚合表 + `benchmark.py`
- **Agentic BI 多智能体协作（20）**：已实现独立 NLP Agent 在内的 6 个 Agent 与 LangGraph 编排
- **分析完整度（20）**：已覆盖描述/诊断/预测/规范四层路径
- **可视化与交互（15）**：已实现 9 类图表与双栏交互界面
- **报告与演示（15）**：已提供完整报告正文、证据生成器、报告模板与演示脚本

## 10. 提交前仍需完成

代码功能已补齐独立 NLP Agent、规范性决策生成、地理图、评论主题图和扩展预聚合层。由于截图和性能数值依赖本地真实数据与 MySQL 环境，提交前仍需：

1. 放入 9 个 CSV，完成 `db_init → etl → refresh_views`。
2. 运行 `python -m utils.benchmark` 和 `python -m utils.evidence_report`。
3. 按 `outputs/reports/submission_evidence.md` 清单将真实运行截图插入 `docs/project_report.md`。
4. 填写小组分工与贡献比例，并记录附录验证问题的实测答案。

## 11. 最终版融合说明

本最终版以成品化界面和文档结构为底座，并强化了以下评分点：

- 将 `mv_*` 从普通 MySQL VIEW 升级为可刷新的物理汇总表，并创建索引，便于证明性能提升。
- 增加评论质量与卖家风险预聚合表：`mv_review_quality`、`mv_seller_review_risk`。
- What-if 分析优先使用 `mv_seller_review_risk` 定位高差评卖家，再回到基础表模拟评分变化。
- `utils.benchmark` 会将性能对比材料写入 `outputs/reports/performance_comparison.md`。

## 12. 验证问题（建议答辩必测）

见：`docs/appendix_validation_queries.md`

建议最少演示：

- `2017 年各州销售额排名怎样？`
- `平台整体准时交付率是多少？哪些州延迟最严重？`
- `哪种支付方式最受欢迎？平均分期数是多少？`
- `根据历史趋势预测未来 6 周销售额。`
- `基于全部分析结果，给出未来 3 个月三大改进策略。`

## 13. 致谢与说明

- 数据集：Olist / Kaggle
- 本项目用于课程期末实践，功能与结论仅用于教学与研究演示
