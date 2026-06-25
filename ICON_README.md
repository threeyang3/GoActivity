# GoActivity 图标说明

## 图标设计

`app_icon.ico` 采用 editorial campus bulletin 风格：

- 深森林绿 `#1a2e23` 圆角矩形背景
- 内部绿色 `#1a5c3a` 圆角矩形
- 白色 "GA" 文字 + 底部 "Activity" 淡字
- 右下角双状态指示灯：上方 = GoActivity，下方 = WeRSS

## 托盘图标双指示灯

GUI 管理器的系统托盘图标有两颗状态指示灯：

| 位置 | 服务 | 颜色含义 |
|------|------|----------|
| 上方圆点 | GoActivity | 🟢 运行中 / 🔴 已停止 / ⚪ 未知 |
| 下方圆点 | WeRSS | 🟢 运行中 / 🔴 已停止 / ⚪ 未知 |

## 重新生成图标

```bash
python generate_icon.py
```

生成多尺寸 ICO（16/32/48/64/128/256）+ PNG 预览。

## 快捷方式图标

运行 `create_shortcut.bat` 会自动为所有快捷方式设置 `app_icon.ico` 图标。

## 图标文件

```
GoActivity/
├── app_icon.ico           # 主图标（多尺寸 ICO）
├── app_icon.png           # PNG 预览
├── app_icon_*.png         # 各尺寸 PNG
├── generate_icon.py       # 图标生成脚本
├── create_shortcut.bat    # 快捷方式创建（含图标设置）
└── ICON_README.md         # 本说明文件
```

## 常见问题

### Q: 图标没有更新？

Windows 图标缓存问题：

1. 按 F5 刷新桌面
2. 或重启资源管理器（任务管理器 → Windows 资源管理器 → 重新启动）
3. 或以管理员运行 `ie4uinit.exe -show`
