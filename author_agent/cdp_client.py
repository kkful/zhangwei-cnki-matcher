"""CDP Proxy 客户端 — 浏览器自动化操作封装

封装 web-access skill 的 CDP Proxy HTTP API (localhost:3456)，
提供浏览器标签管理、JS执行、鼠标点击、键盘输入、页面文本提取等功能。

依赖:
    web-access skill 提供的 CDP Proxy (localhost:3456)
    需要 Chrome 开启远程调试: chrome://inspect/#remote-debugging

核心函数:
    new_tab(url)        - 创建新标签
    eval_js(tab, js)    - 执行 JavaScript
    click_at(tab, sel)  - 真实鼠标点击（CDP Input.dispatchMouseEvent）
    type_text(tab,sel,t) - CDP 物理键盘输入（Input.dispatchKeyEvent）
    page_text(tab)      - 获取页面可见文本
    inject_notification(tab, msg) - 注入红色通知弹窗
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
    except Exception as e:
        return {"error": str(e)}


def _get(endpoint):
    """GET 请求到 CDP Proxy"""
    url = f"{CDP_PROXY}/{endpoint}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


# ── 基本操作 ──

def new_tab(url: str) -> str:
    """创建新 tab，返回 targetId"""
    result = _get(f"new?url={urllib.request.quote(url, safe='')}")
    return result.get("targetId", "")


def close_tab(target_id: str):
    """关闭 tab"""
    return _get(f"close?target={target_id}")


def navigate(target_id: str, url: str):
    """导航到新 URL"""
    return _get(f"navigate?target={target_id}&url={urllib.request.quote(url, safe='')}")


def eval_js(target_id: str, js: str):
    """执行 JS，返回结果"""
    result = _post(f"eval?target={target_id}", js)
    return result.get("value", result.get("error", str(result)))


def click_at(target_id: str, selector: str):
    """真实鼠标点击"""
    return _post(f"clickAt?target={target_id}", selector)


def type_text(target_id: str, selector: str, text: str):
    """模拟键盘输入 — CDP Input.insertText，React 受控组件可用"""
    data = json.dumps({"selector": selector, "text": text})
    return _post(f"type?target={target_id}", data)


def get_info(target_id: str):
    """获取页面信息"""
    return _get(f"info?target={target_id}")


# ── 高级操作 ──

def page_text(target_id: str) -> str:
    """获取页面可见文本"""
    result = eval_js(target_id, "document.body.innerText")
    if isinstance(result, dict) and "error" in result:
        return ""
    return str(result)


def page_title(target_id: str) -> str:
    """获取页面标题"""
    result = eval_js(target_id, "document.title")
    return str(result) if result else ""


def wait_for_load(target_id: str, timeout: float = 5.0):
    """等待页面加载完成"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = eval_js(target_id, "document.readyState")
        if "complete" in str(result):
            return True
        time.sleep(0.5)
    return False


def inject_notification(target_id: str, message: str):
    """在页面注入红色弹窗通知用户"""
    js = f"""
var div = document.createElement('div');
div.style.cssText = 'position:fixed;top:20px;left:50%;transform:translateX(-50%);background:#e74c3c;color:#fff;padding:16px 32px;font-size:16px;border-radius:8px;z-index:999999;box-shadow:0 4px 24px rgba(0,0,0,0.4);text-align:center;max-width:600px;line-height:1.5;font-family:"Microsoft YaHei",sans-serif';
var h = document.createElement('div');
h.style.cssText = 'font-size:20px;margin-bottom:6px;font-weight:bold';
h.textContent = '需要人工介入';
var m = document.createElement('div');
m.textContent = {json.dumps(message, ensure_ascii=False)};
div.appendChild(h);
div.appendChild(m);
document.body.appendChild(div);
"""
    return eval_js(target_id, js)


# ── 知网搜捕 ──

CNKI_ADV_SEARCH = "https://kns.cnki.net/kns8s/AdvSearch"


def search_cnki(target_id: str, author: str, institution: str) -> dict:
    """在知网执行作者发文检索，返回状态"""
    navigate(target_id, CNKI_ADV_SEARCH)
    time.sleep(2)
    wait_for_load(target_id)

    time.sleep(1)
    eval_js(target_id, """
var clicked = false;
var tabs = document.querySelectorAll('li');
tabs.forEach(function(li) {
    if(li.textContent.indexOf('作者发文检索') > -1) {
        li.click();
        clicked = true;
    }
});
JSON.stringify({clicked: clicked, tabCount: tabs.length});
""")
    time.sleep(1.5)

    verify = eval_js(target_id, "document.body.innerText.indexOf('作者发文检索使用方法') > -1")
    tab_switched = "true" in str(verify)

    time.sleep(0.5)
    type_text(target_id, ".input-box:first-child input[type=text]", author)
    time.sleep(0.3)
    type_text(target_id, ".input-box:nth-child(2) input[type=text]", institution)
    time.sleep(0.3)

    click_result = click_at(target_id, ".btn-search")
    if click_result.get("clicked"):
        time.sleep(3)
        wait_for_load(target_id)
        body = page_text(target_id)
        if "共找到" in body or "条结果" in body:
            return {"status": "results", "body": body}

    inject_notification(target_id,
        f"请在浏览器中手动操作：切到「作者发文检索」tab → 填入作者={author}，作者单位={institution} → 点检索。完成后告知。")
    return {"status": "manual_required", "target_id": target_id}


def extract_results_page(target_id: str) -> list:
    """从知网搜索结果页提取论文列表"""
    body = page_text(target_id)
    if "共找到" not in body:
        return []

    result = eval_js(target_id, """
var results = [];
var rows = document.querySelectorAll('tr');
rows.forEach(function(row) {
    var text = row.textContent;
    if(text.indexOf('HTML阅读') > -1 || text.indexOf('原版阅读') > -1) {
        results.push(text.substring(0, 500));
    }
});
JSON.stringify(results.slice(0, 20));
""")
    try:
        return json.loads(str(result))
    except json.JSONDecodeError:
        return []


def open_html_reading(target_id: str) -> str:
    """点击第一个 HTML阅读 链接，返回新 tab 的 targetId"""
    eval_js(target_id, """
var links = document.querySelectorAll('a');
var htmlLink = null;
links.forEach(function(a) {
    if(a.textContent.indexOf('HTML阅读') > -1 && !htmlLink) {
        htmlLink = a;
        a.id = '__cdp_html_target__';
    }
});
""")

    click_result = click_at(target_id, "#__cdp_html_target__")
    if not click_result.get("clicked"):
        return ""

    time.sleep(4)

    targets = _get("targets")
    if isinstance(targets, list):
        for t in targets:
            title = t.get("title", "")
            if "HTML阅读" in title:
                new_id = t.get("targetId", "")
                wait_for_load(new_id)
                return new_id

    return ""


def extract_author_bio(html_tab_id: str) -> str:
    """从 HTML 阅读页提取作者简介"""
    body = page_text(html_tab_id)
    if "作者简介" in body:
        idx = body.index("作者简介")
        snippet = body[idx:idx+500]
        return snippet
    if "作者" in body:
        idx = body.index("作者")
        return body[idx:idx+300]
    return ""


# ── 官网搜捕 ──

def search_official_site(author: str, institution: str) -> str:
    """在搜索引擎中查找官网个人页 URL"""
    query = f'"{author}" "{institution}" 个人主页 教授'
    url = f"https://www.baidu.com/s?wd={urllib.request.quote(query)}"
    return url
