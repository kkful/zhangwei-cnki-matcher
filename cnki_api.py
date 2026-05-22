"""知网搜索 API — 通过 JS fetch 调用 /kns8s/brief/grid API

核心原理:
    在知网页面上下文中执行 fetch，直接调用内部搜索 API。
    使用 Operator:FUZZY 模糊匹配作者单位。

必要前置条件:
    Chrome 远程调试 + CDP Proxy (localhost:3456)

使用:
    from cnki_api import search_cnki_api, ensure_cnki_tab
    tab = ensure_cnki_tab()
    result = search_cnki_api(tab, "张伟", "泰安市中医院")
"""

import json as _json
from cdp_client import eval_js, page_text

SEARCH_JS_TEMPLATE = """
(async function() {{
    var cs = window.cnkiSearch;
    var classid = (window.getDefaultClassid && window.getDefaultClassid()) || 'WD0FTY92';
    var base;
    try {{
        base = JSON.parse(cs.getSearchJsonInfo());
        base.Classid = base.Classid || classid;
        base.Resource = base.Resource || 'CROSSDB';
        if(!base.QNode.QGroup || base.QNode.QGroup.length === 0) {{
            base.QNode.QGroup = [{{Key:"Subject",Title:"",Logic:0,Items:[],ChildItems:[]}}];
        }}
    }} catch(e) {{
        base = {{Platform:"",Resource:"CROSSDB",Classid:classid,Products:"",QNode:{{QGroup:[{{Key:"Subject",Title:"",Logic:0,Items:[],ChildItems:[]}}]}},ExScope:"0",SearchType:"0",Rlang:"CHI",Expands:{{}}}};
    }}

    var qGroup = base.QNode.QGroup[0];
    qGroup.ChildItems = [
        {{
            Key: "input[data-tipid=gradetxt-1]",
            Title: "作者",
            Logic: 0,
            Items: [{{
                Key: "input[data-tipid=gradetxt-1]",
                Title: "作者",
                Logic: 0,
                Field: "AU",
                Operator: "DEFAULT",
                Value: "{author}",
                Value2: ""
            }}],
            ChildItems: []
        }},
        {{
            Key: "input[data-tipid=gradetxt-2]",
            Title: "作者单位",
            Logic: 0,
            Items: [{{
                Key: "input[data-tipid=gradetxt-2]",
                Title: "作者单位",
                Logic: 0,
                Field: "AF",
                Operator: "FUZZY",
                Value: "{institution}",
                Value2: ""
            }}],
            ChildItems: []
        }}
    ];

    var queryJson = JSON.stringify(base);
    var formData = new URLSearchParams();
    formData.append('boolSearch', 'true');
    formData.append('QueryJson', queryJson);

    var resp = await fetch('/kns8s/brief/grid', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}},
        body: formData.toString()
    }});
    var text = await resp.text();

    var countMatch = text.match(/共找到<\\/span>\\s*<em>(\\d+)<\\/em>\\s*<span>条结果/);
    var count = countMatch ? countMatch[1] : '0';

    var titles = [];
    var titleRegex = /<a[^>]*class="fz14"[^>]*>([^<]+)<\\/a>/g;
    var m;
    while(m = titleRegex.exec(text)) {{
        var t = m[1].trim();
        if(t !== '题名' && t !== '作者' && t !== '来源' && t !== '发表时间' && t !== '数据库' && t !== '被引' && t !== '下载' && t !== '操作' && t.length > 3) {{
            titles.push(t);
        }}
    }}

    var authors = [];
    var authorRegex = /<a[^>]*onclick="authorHome[^"]*"[^>]*>([^<]+)<\\/a>/g;
    while(m = authorRegex.exec(text)) authors.push(m[1]);

    var hasHtml = text.indexOf('HTML阅读') > -1;

    return JSON.stringify({{
        count: count,
        titles: titles.slice(0, 20),
        authors: authors.slice(0, 20),
        hasHtml: hasHtml,
        htmlLength: text.length,
        resultHtml: text.substring(0, 100000)
    }});
}})()
"""


def search_cnki_api(tab_id: str, author: str, institution: str = "") -> dict:
    """在已打开的知网 tab 中搜索作者+机构
    
    Args:
        tab_id: CNKI 页面的 CDP targetId
        author: 作者姓名
        institution: 作者单位（可选，使用FUZZY模糊匹配）
    
    Returns:
        {count, titles, authors, hasHtml, resultHtml, ...}
    """
    js = SEARCH_JS_TEMPLATE.replace("{author}", author).replace("{institution}", institution or "")
    js = js.replace("{{", "{").replace("}}", "}")
    result = eval_js(tab_id, js)
    try:
        return _json.loads(str(result))
    except (_json.JSONDecodeError, TypeError):
        return {"count": 0, "error": str(result)[:200]}


def find_primed_cnki_tab() -> str:
    """在所有 Chrome tab 中找已激活的知网页面"""
    from cdp_client import _get, eval_js
    try:
        targets = _get("targets")
        if isinstance(targets, list):
            for t in targets:
                url = t.get("url", "")
                if "cnki.net" in url:
                    tid = t.get("targetId", "")
                    try:
                        check = eval_js(tid, "!!window.cnkiSearch&&!!window.cnkiSearch.getSearchJsonInfo&&(JSON.parse(window.cnkiSearch.getSearchJsonInfo()).Classid||'').length>0")
                        if check and str(check).lower() != "false":
                            return tid
                    except Exception:
                        pass
    except Exception:
        pass
    return ""


def ensure_cnki_tab(tab_id: str = None) -> str:
    """确保知网页面已加载并可用，切换到作者发文检索标签"""
    from cdp_client import new_tab, wait_for_load
    import time

    if not tab_id:
        tab_id = find_primed_cnki_tab()
        if tab_id:
            return tab_id

    if not tab_id:
        tab_id = new_tab("https://kns.cnki.net/kns8s/AdvSearch")
        time.sleep(4)
        wait_for_load(tab_id)

    for i in range(10):
        check = eval_js(tab_id, "!!window.cnkiSearch && !!window.cnkiSearch.getSearchJsonInfo")
        if check and str(check).lower() != "false":
            break
        time.sleep(1)

    # 切换到作者发文检索
    eval_js(tab_id, """
var tabs = document.querySelectorAll('li');
tabs.forEach(function(li) {
    if(li.textContent.indexOf('作者发文检索') > -1) li.click();
});
""")
    time.sleep(0.5)
    return tab_id
