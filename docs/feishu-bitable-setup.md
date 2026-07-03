# 飞书 Bitable 字段参考

> 飞书多维表格"活动库"的字段定义与选项白名单。
> 代码侧以 `app/services/feishu_fields.py` 中的 `SELECT_OPTIONS` 和 `build_record_fields()` 为准。
> 视图配置见 `docs/feishu-bitable-views.md`。

## 字段总览（40 个）

### 基础信息

| 字段 | 类型 | 说明 |
|---|---|---|
| 标题 | Text | 活动名称 |
| 一级分类 | SingleSelect | 见下方选项名册 |
| 二级分类 | SingleSelect | 见下方选项名册 |
| 活动类型 | SingleSelect | 见下方选项名册 |
| 开始时间 | DateTime | 时区 Asia/Shanghai |
| 结束时间 | DateTime | 时区 Asia/Shanghai |
| 活动地点 | Text | |
| 嘉宾 | Text | |
| 主办方 | Text | |
| 摘要 | Text | |
| 报名方式 | Text | |
| 标签 | MultiSelect | 见下方选项名册 |
| 原文链接 | URL | 可点击 |
| 公众号 | Text | 来源公众号名 |
| 封面 | Text | 优先使用公众号推文封面（pic_url） |
| 海报附件 | Attachment | 通过 `lark-cli base +record-upload-attachment` 上传 |
| 状态 | SingleSelect | 见下方选项名册 |
| 时间状态 | SingleSelect | 见下方选项名册 |
| 保留决策 | SingleSelect | 见下方选项名册 |
| 用户置顶 | Checkbox | |
| 用户参与 | Checkbox | 用户标记"我参与了"，阻止自动归档 |
| 置信度 | Number | 0~1，精度 2 位 |
| 归档时间 | DateTime | 归档时自动填写，时区 Asia/Shanghai |
| 关联原因 | Text | 仅非活动时填 |
| 更新时间 | DateTime | 时区 Asia/Shanghai |

### 详情信息

| 字段 | 类型 |
|---|---|
| 演出类型 | Text |
| 演出作品 | Text |
| 演出团体 | Text |
| 票价信息 | Text |
| 讲座主题 | Text |
| 主讲人头衔 | Text |
| 讲座系列 | Text |
| 比赛名称 | Text |
| 比赛类型 | Text |
| 截止时间 | Text |
| 奖项设置 | Text |
| 报名链接 | URL |
| 报名截止 | Text |
| 人数限制 | Text |

## Select 选项名册

> **必须精确一致**，区分全角/半角与中点 `·` (U+00B7)。
> 代码位置：`app/services/feishu_fields.py` → `SELECT_OPTIONS`

### 一级分类
讲座 / 演出 / 比赛 / 招募 / 展览 / 工作坊 / 分享会 / 其他

### 二级分类
学术 / 科技 / 艺术 / 公益 / 体育 / 娱乐 / 招聘 / 其他

### 活动类型
讲座 / **演出·放映** / **比赛·征稿** / 志愿者招募 / 普通招募 / 普通活动 / 非活动

> ⚠️ "演出·放映"和"比赛·征稿"用的是中点 `·` (U+00B7)，不是斜杠 `/`。

### 状态
pending / pending_ai / extracted / synced / failed_sync / failed_extract / ignored_non_event / expired_hidden / filtered_out / needs_image_retry / archived

### 时间状态
unknown / scheduled / ongoing / ended / expired / upcoming / past

### 保留决策
keep / keep_user / keep_recap / keep_recap_lowest / drop_past_event / skip_older_than_30_days / skip_older_than_60_days / auto_archived / user_archived

### 标签
免费 / 收费 / 线上 / 线下 / 报名中 / 已截止 / 需审核 / 学生专属 / 公开 / 校内 / 推荐

## 写入格式

代码通过 `build_record_fields()` 构建 payload，格式如下：

| 字段类型 | 写入格式 | 示例 |
|---|---|---|
| SingleSelect | 纯字符串 | `"讲座"` |
| MultiSelect | 字符串列表 | `["免费", "线下"]` |
| DateTime | 字符串 | `"2026-06-18 19:00:00"` |
| URL | 纯字符串 | `"https://example.com"` |
| Number | 浮点数 | `0.87` |
| Checkbox | 布尔值 | `false` |
| Text | 纯字符串 | `"北大团委"` |

> 海报附件不走 record payload，通过 `lark-cli base +record-upload-attachment` 单独上传。

## 自动创建/更新视图

```bash
curl -X POST http://localhost:8000/setup/feishu-views
```

幂等操作：已存在的视图跳过，不存在的创建。返回示例：

```json
{
  "total": 11,
  "created": 0,
  "skipped": 10,
  "failed": 0
}
```

视图设计详见 `docs/feishu-bitable-views.md`。

## 排障

### 写入失败 code=1254000 "field value type mismatch"
字段类型不对。确认 Select 字段是 SingleSelect/MultiSelect，DateTime 字段是 DateTime 类型。

### 写入失败 code=1254002 "options not match"
Select 字段的某个选项没建。对照上方选项名册与飞书字段设置是否一致。

### "标签"全部丢失
检查 `GET /sync/logs?target=feishu_event` 的 stderr，看 `multi-select field '标签'` 的 warning，确认是哪些 tag 不在白名单。

### 日历视图打开是空的
检查"开始时间"字段是否为 DateTime 类型且时区为 Asia/Shanghai。

### 海报没传
- `FEISHU_PROVIDER=lark_cli`：通过 `+record-upload-attachment` 上传，检查日志
- `FEISHU_PROVIDER=openapi`：OpenAPI 不支持附件上传（需 multipart），换 `lark_cli` 或在飞书 UI 手动上传

### POST /setup/feishu-views 部分失败
检查返回 JSON 中 `action="failed"` 的视图，`error` 字段显示具体原因：
- "permission denied" → 飞书应用没有 Bitable 写权限
- "field not found" → 视图配置里的字段名与飞书表字段名不一致
- "timeout" → lark-cli 执行超时，重试即可

### Select 字段值被跳过
日志中出现 `option 'xxx' not in whitelist, skipping` → 该选项不在 `SELECT_OPTIONS` 白名单中。检查 `app/services/feishu_fields.py` 并对比飞书端选项。
