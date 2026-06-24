# 添加公众号指南

本文档说明如何在 GoActivity 系统中添加新的微信公众号。

## 前置条件

- we-mp-rss 服务已启动并运行
- GoActivity 服务已启动
- 已获取 we-mp-rss 的 Access Key 和 Secret Key

## 步骤一：在 we-mp-rss 中订阅公众号

1. 访问 we-mp-rss 管理界面：`http://localhost:8001`
2. 登录后进入「公众号管理」页面
3. 点击「添加公众号」
4. 输入公众号名称或微信号
5. 等待 we-mp-rss 完成订阅和授权

## 步骤二：配置 GoActivity 拉取

在 `.env` 文件中确认以下配置：

```env
WE_MP_RSS_BASE_URL=http://localhost:8001
WE_MP_RSS_API_BASE=/api/v1/wx
WE_MP_RSS_ACCESS_KEY=WK...
WE_MP_RSS_SECRET_KEY=SK...
```

## 步骤三：拉取历史文章

新订阅的公众号需要拉取历史文章：

```bash
# 拉取最近 50 篇文章
curl -X POST "http://localhost:8000/sync/we-mp-rss/articles?limit=50"

# 或者通过 RSS 方式拉取（不需要 AK/SK）
curl -X POST "http://localhost:8000/sync/we-mp-rss/rss/all?limit=50"
```

## 步骤四：验证抽取结果

1. 访问 Web 管理后台：`http://localhost:8000/`
2. 查看「活动列表」中的新活动
3. 检查抽取结果是否正确
4. 如有错误，可手动触发重新抽取

## 步骤五：同步到飞书

```bash
# 手动触发同步
curl -X POST "http://localhost:8000/sync/auto"
```

或在 Web 管理后台点击「触发同步」按钮。

## 常见问题

### Q: 新公众号的文章没有被自动拉取？

A: 检查以下几点：
1. we-mp-rss 是否已成功订阅该公众号
2. `AUTO_SYNC_CRON` 配置是否正确（默认每小时一次）
3. 查看同步日志：`GET /sync/runs/latest/we-mp-rss-json`

### Q: 文章被分类为「非活动」？

A: 这是正常行为。系统会自动过滤宣传类、回顾类文章。如果确实是活动但被误判：
1. 在 Web 管理后台找到该活动
2. 点击「置顶」按钮，系统会保留该活动
3. 或者在飞书多维表格中手动修改「保留决策」字段

### Q: 活动信息抽取不准确？

A: 可以通过以下方式修正：
1. 在 Web 管理后台查看活动详情
2. 点击「重新抽取」按钮
3. 或者在飞书多维表格中手动修正字段

## 批量添加公众号

如果需要批量添加多个公众号，可以使用以下脚本：

```python
import requests

# 公众号列表
accounts = [
    "北大团委",
    "北京大学百周年纪念讲堂",
    "北京大学人文学部",
    # 添加更多...
]

# 拉取每个公众号的文章
for account in accounts:
    try:
        response = requests.post(
            "http://localhost:8000/sync/we-mp-rss/articles",
            params={"limit": 100}
        )
        print(f"{account}: {response.json()}")
    except Exception as e:
        print(f"{account} 失败: {e}")
```

## 最佳实践

1. **定期检查**：每周检查一次新公众号的抽取结果
2. **及时修正**：发现错误及时修正，避免脏数据积累
3. **优化规则**：如果发现大量误判，考虑优化分类规则
4. **备份数据**：定期备份 `storage/app.db` 文件
