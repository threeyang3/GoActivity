# 飞书 Bitable 字段迁移操作清单

> 本文档配合 GoActivity V1.1 字段重塑使用。代码侧已就绪，需要在飞书端按顺序完成一次性手工迁移。**先做后两步（dry-run + 真跑），后做中间步骤的话会导致写入失败。**

## 1. 备份

1. 打开"活动库" Bitable
2. 右上 `···` → 导出为 Excel / CSV
3. 备份到 `storage/feishu-backup-<日期>.xlsx`

## 2. 新增字段

按下方清单在表格顶部或任意位置新建 7 列（顺序无所谓；建议放最后便于对比）：

| 字段名（中文） | 类型 | 备注 |
|---|---|---|
| 公众号 | Text | 写 `Article.mp_name` |
| 时间状态 | SingleSelect | 详见 §3 选项名册 |
| 保留决策 | SingleSelect | 详见 §3 选项名册 |
| 用户置顶 | Checkbox | 是否人工置顶 |
| 置信度 | Number | 精度 2 位 |
| 关联原因 | Text | 仅非活动时填 |
| ~~活动类型编码~~ | **不要建** | 这是要删的旧列 |

## 3. 建 SingleSelect / MultiSelect 选项

对每个 Select 字段，进入字段设置 → 选项管理 → 新增下列选项（**必须精确一致，区分全角/半角与中点**）。

### 一级分类
讲座 / 演出 / 比赛 / 招募 / 展览 / 工作坊 / 分享会 / 其他

### 二级分类
学术 / 科技 / 艺术 / 公益 / 体育 / 娱乐 / 招聘 / 其他

### 活动类型
讲座 / **演出·放映** / **比赛·征稿** / 志愿者招募 / 普通招募 / 普通活动 / 非活动

> ⚠️ 注意"演出·放映"和"比赛·征稿"用的是中点 `·` (U+00B7)，不是斜杠 `/`。
> 这两个选项必须严格与代码 `SELECT_OPTIONS["活动类型"]`（`app/services/feishu_fields.py`）中的字符一致，否则 `select_text` 会跳过该字段。

### 状态
pending / extracted / synced / failed_sync / failed_extract / ignored_non_event

### 时间状态
unknown / scheduled / ongoing / ended / expired

### 保留决策
keep / remove / pending_review

### 标签
免费 / 收费 / 线上 / 线下 / 报名中 / 已截止 / 需审核 / 学生专属 / 公开

## 4. 改字段类型（不可逆）

对已有字段逐一修改（右键 → 编辑字段 → 类型）：

| 列名 | 旧类型 | 新类型 | 设置 |
|---|---|---|---|
| 一级分类 | Text | SingleSelect | 引用 §3 选项 |
| 二级分类 | Text | SingleSelect | 引用 §3 选项 |
| 活动类型 | Text | SingleSelect | 引用 §3 选项 |
| 开始时间 | Text | DateTime | 时区 Asia/Shanghai，含日期+时间 |
| 结束时间 | Text | DateTime | 时区 Asia/Shanghai |
| 地点 | Text | Location | — |
| 标签 | Text | MultiSelect | 引用 §3 选项 |
| 原文链接 | Text | URL | — |
| 状态 | Text | SingleSelect | 引用 §3 选项 |
| 更新时间 | Text | DateTime | 时区 Asia/Shanghai |

> 报名方式 / 嘉宾 / 主办方 / 摘要 保持 Text。

> ⚠️ **改类型不可逆**。改之前确保已备份。改完后飞书会尝试把现有文本值匹配到选项，匹配不到会留空（不影响后续写入）。

## 5. 设置时区

对"开始时间" / "结束时间" / "更新时间"三个 DateTime 字段：

字段编辑 → 时区 → **Asia/Shanghai**

> 原因：GoActivity 写入的是 UTC 毫秒时间戳，但业务时区是上海。飞书 DateTime 字段在 UI 显示时会按字段时区渲染，Asia/Shanghai 能保证显示正确。

## 6. 海报附件字段确认

确认 `海报附件` 字段：

1. 类型必须是 **Attachment（附件）**
2. 勾选"允许上传多文件"
3. 不在 record 写入 payload 里出现（只能走 `lark-cli base +record-upload-attachment`）

如果该字段当前是别的类型，改成 Attachment 即可。

## 7. 删除旧列

以下两列新代码不再写入，可直接删除：

- `活动类型编码` — 新代码只写 `活动类型` SingleSelect
- `海报`（如确知所有海报已迁移到"海报附件"）— 旧文本路径列已无意义

> 保守做法：先保留"海报"列观察一周，确认无数据回流再删。

## 8. dry-run 验证 payload 结构

代码侧配置：

```env
FEISHU_DRY_RUN=true
FEISHU_PROVIDER=lark_cli
```

启动 uvicorn 后：

```bash
# 拉一条新文章
curl -X POST http://localhost:8000/sync/we-mp-rss/articles

# 看飞书写入日志
curl http://localhost:8000/sync/logs?target=feishu_event | python -m json.tool
```

在 `stdout` 字段中检查 `payload` 结构（关键检查点）：

- [ ] `"活动类型"` 是 `{"text": "..."}` 对象（不是字符串）
- [ ] `"标签"` 是 `[{...}]` 列表（不是 `", ".join(...)` 字符串）
- [ ] `"开始时间"` / `"结束时间"` / `"更新时间"` 是 13 位整数（毫秒）
- [ ] `"原文链接"` 是 `{"text": "阅读全文", "link": "https://..."}`
- [ ] `"地点"` 是 `{"address": "..."}` 对象
- [ ] `"状态"` / `"时间状态"` / `"保留决策"` 是 `{"text": "..."}` 对象
- [ ] `"置信度"` 是 0~1 的小数
- [ ] `"用户置顶"` 是 `true` / `false`（如果有的话）
- [ ] **payload 里没有 `"海报"` 键**（关键回归）
- [ ] **payload 里没有 `"活动类型编码"` 键**（关键回归）
- [ ] payload 里**有** `"公众号"` / `"时间状态"` / `"保留决策"` / `"用户置顶"` / `"置信度"` / `"关联原因"`

如果某个 Select 字段写了空字符串进 payload，说明飞书端该字段的某个选项没建对。检查 `GET /sync/logs` 的 stderr 看 warning：

```text
feishu select field '一级分类': option '未分类' not in whitelist, skipping
```

## 9. 真跑 + 飞书端核对

```env
FEISHU_DRY_RUN=false
```

挑 3 条不同 `activity_kind` 的活动触发同步（`POST /events/{id}/sync-feishu`），然后人工核对飞书 Bitable：

- [ ] "海报附件"列有图、"海报"列已空
- [ ] "开始时间"在日历视图能拖动到正确日期
- [ ] "原文链接"是蓝色可点击链接
- [ ] "标签"是彩色 chip
- [ ] "状态" / "活动类型" / "时间状态"是彩色标签、可用颜色过滤
- [ ] "公众号"列显示公众号名（如"北大团委"）
- [ ] "置信度"显示 0~1 小数
- [ ] "用户置顶"是勾选框

## 10. 自动创建视图（可选）

字段迁移完成后，可以用代码自动创建 11 个视图（幂等：已存在则跳过）：

```bash
# 确认服务已启动，然后：
curl -X POST http://localhost:8000/setup/feishu-views
```

返回示例：

```json
{
  "total": 11,
  "created": 11,
  "skipped": 0,
  "failed": 0,
  "results": [
    {"name": "活动日历", "action": "created", "view_id": "view_xxx", "error": ""},
    {"name": "待审核看板", "action": "created", "view_id": "view_yyy", "error": ""}
  ]
}
```

再次调用会跳过已存在的视图：

```bash
curl -X POST http://localhost:8000/setup/feishu-views
# {"total":11,"created":0,"skipped":11,"failed":0,...}
```

> 如果不想用 API，也可以按 `docs/feishu-bitable-views.md` 手动在飞书 UI 创建视图。

## 11. 排障

### 写入失败 code=1254000 "field value type mismatch"
说明字段类型没改。回到 §4。

### 写入失败 code=1254002 "options not match"
说明 Select 字段的某个选项没建。检查 `SELECT_OPTIONS`（`app/services/feishu_fields.py`）与飞书字段设置是否一致。

### "标签"全部丢失
检查 `GET /sync/logs?target=feishu_event` 的 stderr，看 `multi-select field '标签'` 的 warning，确认是哪些 tag 不在白名单。

### 日历视图打开是空的
检查"开始时间"字段时区是否设为 Asia/Shanghai（§5），以及该字段是否被改成了 DateTime（§4）。

### OpenAPI provider 跑完后海报没传
预期行为。OpenAPI 不实现附件上传（需要 multipart，本期不做）。看日志：

```text
WARNING: Feishu OpenAPI provider does not upload poster attachments; poster images for event <id> were not uploaded.
```

解决：换 `FEISHU_PROVIDER=lark_cli` 跑这条事件，或在飞书 UI 手动上传。

### POST /setup/feishu-views 部分失败
检查返回 JSON 中 `action="failed"` 的视图，`error` 字段会显示具体原因。常见问题：
- "permission denied" → 飞书应用没有 Bitable 写权限
- "field not found" → 视图配置里的字段名与飞书表字段名不一致
- "timeout" → lark-cli 执行超时，重试即可
