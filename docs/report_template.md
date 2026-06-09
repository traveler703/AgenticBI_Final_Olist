# Agentic BI 期末项目报告模板

> 已填写的完整正文见 `docs/project_report.md`，本模板用于核对结构与补充小组信息。

## 1. 项目背景与动机
- 业务背景
- Agentic BI 价值
- 项目目标

## 2. 系统架构设计
- 三层架构图（data_layer / backend / frontend，建议 mermaid）
- 两个物理隔离数据库与多账号读写隔离
- 多 Agent 职责与调用关系（supervisor + 数据/预测/What-if/异常/诊断/评论/可视化/元）

## 3. 技术选型说明
- LLM：DeepSeek / Ollama 可切换
- Agent 编排：LangGraph StateGraph + MemorySaver
- 查询引擎：MySQL 8（Docker，多账号）
- 预测模型：对数尺度阻尼 Holt 趋势
- 前端：Vite + ECharts；后端 FastAPI + SSE

## 4. 数据集描述与预处理
- Olist 9 张核心表
- 清洗规则与 `fact_order_items` 构建
- 衍生字段：item_gmv / year_month / shipping_duration_days / is_on_time
- 一键编排：`python -m utils.init_db`

## 5. 物理预聚合表设计（重点）
- 11 张 `mv_*` 与各自粒度、用途
- SQL 见 `data_layer/sql/02_preaggregation.sql`
- 口径铁律（加权聚合）

## 6. Agent 查询策略与自我纠错
- 预聚合优先匹配、基础表回退、只读 SQL 安全约束
- 不使用黄金 SQL，纯 LLM ReAct + 自我修正
- Plan-Execute-Reflect-Replan 闭环与反思要点

## 7. 四层分析结果
- 描述性 / 诊断性 / 预测性 / 规范性
- 地理气泡、配送诊断、What-if、异常检测

## 8. 可视化与交互
- 12 类图表与 LLM 决策选型
- 三栏界面（历史 / 对话 / 图表+SQL）
- 组合型问题的自我纠错示例

## 9. 性能优化与对比
- 原表 JOIN vs 物理预聚合
- `python -m scripts.benchmark_preagg` 输出与加速比

## 10. 技术挑战与解决方案
- 组合型规划稳定性、协调器拆分、SQL 生成、预测边界、代理导致 LLM 中断等

## 11. 小组分工与比例
- 成员 A / B / C / D 与贡献占比

## 12. 总结与展望
- 已完成成果
- 可拓展方向
