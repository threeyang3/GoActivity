# 桌面管理程序

## 概述

GoActivity 桌面管理程序使用 PySide6 构建，提供系统托盘图标、服务控制和状态监控。
当前推荐入口为 `python -m desktop.app`。

## 安装

```bash
pip install -r requirements-desktop.txt
```

## 启动

```bash
python -m desktop.app
```

## 功能

### 系统托盘

- 双状态指示灯（GoActivity + WeRSS）
- 颜色含义：
  - 🟢 绿色：正常运行
  - 🟡 黄色：启动中或降级
  - 🔴 红色：停止或错误
  - ⚪ 灰色：未知

### 托盘菜单

- 打开控制中心
- 打开管理后台
- 立即同步
- GoActivity 启动/停止/重启
- WeRSS 启动/停止/重启
- 日志
- 退出

### 控制中心

- 概览：服务状态、快捷操作
- 服务：详细状态、启动/停止/重启
- 配置：系统信息

## 单实例

程序使用 TCP 端口锁确保只有一个实例运行。第二个实例启动时会提示"已在运行"。

## 自动重启

服务崩溃后自动重启，最多 3 次，指数退避。

## 路径配置

程序自动检测 Python 解释器和工作目录，不再硬编码绝对路径。
`start_service.py` 已改为文件日志输出，避免 stdout `PIPE` 阻塞。
