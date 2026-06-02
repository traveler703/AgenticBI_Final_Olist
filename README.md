# Agentic BI — Olist 多表电商运营分析与决策智能系统

基于 Olist 电商公开数据集，实现面向业务人员的自然语言分析系统。  
系统采用 **LangGraph 多智能体编排 + MySQL 物理预聚合表 + DeepSeek LLM + Streamlit 双栏仪表板**，覆盖描述性、诊断性、预测性、规范性四层分析。

## 1. 项目目标（对齐期末要求）

- 支持自然语言提问，自动执行跨表分析与 SQL 查询
- 物理预聚合层加速高频统计查询，支持“预聚合优先 + 原表回退”
- 多智能体协作完成：数据分析、可视化、决策建议与流程调度
- 输出图表、SQL、数据摘要与可执行运营建议
- 支持多轮对话上下文（基于 `MemorySaver`）

## 2. 当前功能概览

### 2.1 物理预聚合表（已实现）

- `mv_monthly_sales`
- `mv_state_sales`
- `mv_category_sales`
- `mv_delivery_perf`
- `mv_payment_dist`
- `mv_review_quality`
- `mv_seller_review_risk`

对应 SQL 定义见：`utils/sql/create_materialized_views.sql`  
刷新脚本：`python -m utils.refresh_views`

### 2.2 多智能体架构（已实现）

- `coordinator`：问题路由与流程协调
- `data_analyst`：自然语言转 SQL，优先命中 `mv_*`，失败回退原表
- `visualizer`：生成标准图表输出
- `whatif_anomaly`：加分模块（What-if / 异常检测）
- `decision`：汇总分析并输出策略建议

编排入口：`agents/graph.py`（`StateGraph` + `MemorySaver`）

### 2.3 可视化能力（已实现）

当前已集成不少于 6 类图表（见 `agents/visualizer.py`）：

- 月度销售趋势（含预测曲线）
- 州销售额柱状图
- 支付方式柱状图
- 支付方式 × 分期数热力图
- 商品重量 × 运费散点图
- 准时交付率趋势图

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
streamlit run dashboard/app.py
```

也可使用入口脚本：

```bash
python app.py
```

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
- **预聚合视图设计与性能优化（10）**：已实现 7 个物理预聚合表 + `benchmark.py`
- **Agentic BI 多智能体协作（20）**：已实现 4+ Agent 与 LangGraph 编排
- **分析完整度（20）**：已覆盖描述/诊断/预测/规范四层路径
- **可视化与交互（15）**：已实现 6+ 图表与双栏交互界面
- **报告与演示（15）**：已提供 `docs/report_template.md` 与 `docs/demo_script.md`

## 10. 仍需完善（建议优先级）

以下是按“期末项目提交”视角建议补强的内容：

1. **报告证据链补全（高优先级）**
   - 需要在项目报告中补齐：架构图、关键页面截图、附录问题实测结果
   - 特别是“同一查询有/无物理预聚合表”的耗时截图与加速结论

2. **诊断与规范分析可解释性（高优先级）**
   - 在结果页固定展示：命中数据源（`mv_*` 或 base）、SQL、核心指标口径
   - 让答辩时更容易证明“预聚合优先策略”真实生效

3. **可视化类型进一步贴合课程描述（中优先级）**
   - 当前 6 类图表已达标，但可补充地理热力图/州级气泡图以增强说服力

4. **异常与 What-if 的演示闭环（中优先级）**
   - 建议准备 1-2 个固定演示问题与截图，避免现场触发不稳定

5. **工程质量补充（中优先级）**
   - 增加关键模块单元测试（SQL 安全、回退逻辑、预测输出格式）
   - 增加一份“常见报错与排查”文档，提升复现成功率

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
