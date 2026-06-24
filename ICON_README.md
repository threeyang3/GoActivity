# GoActivity 图标说明

## 可用图标

项目提供了两种风格的图标：

### 1. 圆形风格 (`app_icon.ico`)
- 圆形背景
- 渐变蓝色配色
- "GA" 文字标识
- 绿色装饰元素

### 2. 现代方形风格 (`app_icon_modern.ico`)
- 圆角方形背景
- 渐变蓝色配色
- "GA" 文字标识
- 绿色装饰线条和点

---

## 更换图标

### 方法一：使用更换工具（推荐）

```bash
# 运行图标更换工具
change_icon.bat
```

选择想要的图标风格即可。

### 方法二：手动更换

1. 右键点击桌面快捷方式
2. 选择"属性"
3. 点击"更改图标"
4. 浏览到项目目录，选择 `app_icon.ico` 或 `app_icon_modern.ico`
5. 点击"确定"

---

## 系统托盘图标

GUI 管理器的系统托盘图标会根据服务状态显示不同颜色：

| 颜色 | 状态 |
|------|------|
| 🟢 绿色 | 服务运行中 |
| 🔴 红色 | 服务已停止 |
| ⚪ 灰色 | 状态未知 |

系统托盘图标会自动加载 `app_icon.ico` 文件。

---

## 创建自定义图标

如果想创建自己的图标，可以修改 `create_icon.py` 文件：

```python
# 修改颜色
primary_color = (52, 152, 219, 255)  # 蓝色
accent_color = (46, 204, 113, 255)   # 绿色

# 修改文字
draw.text((x, y), "GA", fill=text_color, font=font)

# 保存
image.save('my_icon.ico', format='ICO')
```

然后运行：
```bash
python create_icon.py
```

---

## 图标文件位置

```
GoActivity/
├── app_icon.ico           # 圆形风格图标
├── app_icon_modern.ico    # 现代方形风格图标
├── create_icon.py         # 图标生成脚本
├── change_icon.bat        # 图标更换工具
└── ICON_README.md         # 本说明文件
```

---

## 常见问题

### Q: 图标没有更新？

**Windows 图标缓存问题**：

1. **刷新桌面**：按 F5 刷新桌面
2. **重启资源管理器**：
   - 打开任务管理器
   - 找到"Windows 资源管理器"
   - 右键选择"重新启动"
3. **清除图标缓存**：
   ```bash
   # 以管理员身份运行
   ie4uinit.exe -show
   ```

### Q: 如何恢复默认图标？

运行 `change_icon.bat`，选择想要的风格即可。

### Q: 可以使用自己的图标吗？

可以！将你的 `.ico` 文件放到项目目录，然后：
1. 重命名为 `app_icon.ico`
2. 运行 `change_icon.bat` 选择风格 1

---

## 技术说明

图标使用 PIL (Pillow) 库生成，支持：
- 多尺寸 ICO 文件 (16x16 到 256x256)
- 渐变背景
- 抗锯齿文字
- 透明度

---

**提示**：更换图标后可能需要刷新桌面或重启资源管理器才能看到变化。
