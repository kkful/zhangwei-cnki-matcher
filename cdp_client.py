"""CDP Proxy 客户端 — 浏览器自动化操作封装

封装 web-access skill 的 CDP Proxy HTTP API (localhost:3456)，
提供浏览器标签管理、JS执行、页面文本提取等功能。

依赖:
    web-access skill 提供的 CDP Proxy (localhost:3456)
    需要 Chrome 开启远程调试: chrome://inspect/#remote-debugging

核心函数:
    new_tab(url)     - 创建新标签
    eval_js(tab, js) - 执行 JavaScript
    page_text(tab)   - 获取页面可见文本
    close_tab(tab)   - 关闭标签
"""

import json
import time
import urllib.request
import urllib.error

CDP_PROXY = "http://localhost:3456"


def _post(endpoint, data=None):
    """POST 请求到 CDP Proxy"""
    url = f"{CDP_PROXY}/{endpoint}"
    body = data.encode("utf-8") if isinstance(data, str) else None
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "text/plain")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}"}


def _get(endpoint):
    """GET 请求到 CDP Proxy"""
    url = f"{CDP_PROXY}/{endpoint}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}"}


def new_tab(url: str) -> str:
    """创建新标签并等待加载，返回 targetId"""
    r = _get(f"new?url={url}")
    return r.get("targetId", "")


def eval_js(tab_id: str, js: str) -> str:
    """在指定标签中执行 JavaScript，返回结果"""
    r = _post(f"eval?target={tab_id}", js)
    return r.get("value", str(r))


def page_text(tab_id: str) -> str:
    """获取页面可见文本（document.body.innerText）"""
    return eval_js(tab_id, "document.body.innerText")


def close_tab(tab_id: str):
    """关闭标签"""
    return _get(f"close?target={tab_id}")


def wait_for_load(tab_id: str, timeout: int = 10):
    """等待页面加载完成"""
    for i in range(timeout):
        try:
            r = eval_js(tab_id, "document.readyState")
            if r == "complete":
                return True
        except:
            pass
        time.sleep(0.5)
    return False
