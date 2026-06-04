# 常见问题与排查

## 数据未就绪

确认 `data/raw/` 中包含 README 列出的 9 个 CSV，然后依次执行：

```bash
python -m utils.db_init
python -m utils.etl
python -m utils.refresh_views
```

## MySQL 连接失败

检查 Docker 容器、端口、用户名、密码和数据库名；随后使用 `python -m utils.evidence_report` 验证物理表状态。

## DeepSeek 不可用

SQL 高频问题会自动使用安全模板，决策 Agent 会使用确定性分段建议兜底。配置 API Key 后可获得更贴合上下文的总结和建议。

## 图表缺失

先刷新全部物理预聚合表，再在仪表板点击“生成默认图表”。新增地理图依赖 `geolocation` 表，评论主题图依赖非空评论正文。

## 提交证据不完整

运行：

```bash
python -m utils.benchmark
python -m utils.evidence_report
```

然后按照 `outputs/reports/submission_evidence.md` 的人工截图清单补齐报告证据。
