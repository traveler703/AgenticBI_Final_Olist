# Agentic BI 期末项目报告模板

## 1. 项目背景与动机
- 业务背景
- Agentic BI 价值
- 项目目标

## 2. 系统架构设计
- 总体架构图（建议使用 mermaid 或 draw.io）
- 多 Agent 职责与调用关系
- MySQL 基础表与物理预聚合层关系

## 3. 技术选型说明
- LLM：DeepSeek
- Agent 编排：LangGraph StateGraph（单轮状态隔离）
- 查询引擎：MySQL（Docker）
- 预测模型：基于完整周度序列的对数尺度阻尼 Holt 趋势
- 可视化与前端：Streamlit + Matplotlib

## 4. 数据集描述与预处理
- Olist 9 张核心表说明
- 清洗步骤
- `fact_order_items` 构建逻辑
- 异常值与缺失值处理

## 5. 物理预聚合表设计（重点）
- `mv_monthly_sales`
- `mv_weekly_sales`
- `mv_state_sales`
- `mv_category_sales`
- `mv_delivery_perf`
- `mv_payment_dist`
- `mv_review_quality`
- `mv_seller_review_risk`

附：关键 SQL 片段可来自 `utils/sql/create_materialized_views.sql`。

## 6. Agent 查询策略
- 物理预聚合表优先匹配规则
- 回退机制（宽表/基础表）
- SQL 安全约束（仅 SELECT）

## 7. 四层分析结果
- 描述性分析
- 诊断性分析
- 预测性分析（未来 6 周，区分单周值与 6 周合计）
- 规范性分析（运营建议）

## 8. 可视化与交互
- 六类图表展示截图
- 左聊右图交互界面说明
- 单轮复合问题上下文传递示例

## 9. 性能优化与对比（重点）
- 对比查询：原表实时聚合 vs 物理表 `mv_monthly_sales`
- 记录 `utils/benchmark.py` 输出
- 放入执行耗时截图与加速比结论

## 10. 技术挑战与解决方案
- SQL 生成准确性
- 大表 JOIN 性能
- 评论文本噪声处理

## 11. 小组分工与比例
- 成员 A：
- 成员 B：
- 成员 C：

## 12. 总结与展望
- 已完成成果
- 可拓展方向（What-if / 异常检测 Agent）
