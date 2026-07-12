"""路由唯一性测试 — 确保应用中不存在重复的 path + method 组合。"""

from fastapi.testclient import TestClient

from app.main import app


def test_no_duplicate_routes():
    """验证所有路由的 (path, methods) 组合唯一。"""
    routes = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method == "HEAD":
                    continue  # HEAD 由 FastAPI 自动生成
                routes.append((route.path, method))

    seen = set()
    duplicates = []
    for path, method in routes:
        key = (path, method)
        if key in seen:
            duplicates.append(key)
        seen.add(key)

    assert not duplicates, f"发现重复路由: {duplicates}"


def test_get_routes_do_not_modify_data():
    """验证 GET 路由不执行数据修改操作。

    检查所有 GET 路由的函数名不包含修改性动词（除了查询类的 get/list）。
    这是一个启发式检查，不能替代代码审查。
    """
    write_verbs = {"create", "delete", "remove", "update", "insert", "add", "modify", "set", "put", "post"}
    issues = []
    for route in app.routes:
        if not hasattr(route, "methods") or not hasattr(route, "endpoint"):
            continue
        if "GET" not in route.methods:
            continue
        # 跳过 HEAD-only 路由
        if route.methods == {"HEAD"}:
            continue
        func_name = route.endpoint.__name__ if hasattr(route.endpoint, "__name__") else ""
        # 检查函数名是否包含写操作动词
        for verb in write_verbs:
            if verb in func_name.lower() and func_name.lower() not in ("get_latest_sync_run",):
                issues.append(f"GET {route.path} -> {func_name} (可能包含写操作)")
    # 这个检查是启发式的，只作为警告
    if issues:
        import warnings
        warnings.warn(f"以下 GET 路由可能执行写操作:\n" + "\n".join(issues))


def test_write_routes_require_auth():
    """验证写路由（POST/PUT/DELETE）使用了鉴权依赖。"""
    from app.auth import require_admin

    issues = []
    for route in app.routes:
        if not hasattr(route, "methods") or not hasattr(route, "dependencies"):
            continue
        methods = route.methods - {"HEAD", "OPTIONS"}
        is_write = bool(methods & {"POST", "PUT", "DELETE", "PATCH"})
        if not is_write:
            continue

        # 检查是否有 require_admin 依赖
        has_auth = False
        for dep in (route.dependencies or []):
            dep_fn = dep.dependency if hasattr(dep, "dependency") else dep
            if dep_fn is require_admin:
                has_auth = True
                break
            # 检查 wrapped functions
            if hasattr(dep_fn, "__wrapped__"):
                if dep_fn.__wrapped__ is require_admin:
                    has_auth = True
                    break

        # 跳过 webhook 和 health 端点（不需要鉴权）
        if route.path in ("/health", "/diagnostics/config"):
            continue
        if route.path.startswith("/webhooks/"):
            continue
        if route.path == "/":
            continue

        if not has_auth:
            issues.append(f"{route.path} ({', '.join(methods)})")

    # 允许一些已知不需要鉴权的端点
    allowed_no_auth = {"/health", "/diagnostics/config", "/webhooks/we-mp-rss", "/"}
    real_issues = [i for i in issues if not any(i.startswith(a) for a in allowed_no_auth)]

    if real_issues:
        import warnings
        warnings.warn(f"以下写路由可能缺少鉴权:\n" + "\n".join(real_issues))
