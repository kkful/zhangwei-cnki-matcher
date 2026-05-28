"""张伟名称规范 - 种子画像驱动的知网定向检索+实体对齐（稳健版）

每处理一个画像立即保存，崩溃不丢数据。
支持断点续跑、分批处理、作者简介提取。

Usage:
  python pipeline.py --dep E:\旧规范文档 --input 张伟.xlsx --output matched.xlsx
  python pipeline.py --start 0 --end 10                     # 分批处理
  python pipeline.py --start 96                              # 断点续跑
"""
import sys, os, json, time, re, random, urllib.request, traceback
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

# === 可配置路径（命令行参数可覆盖） ===
_args = sys.argv[1:]
DEP_PATH    = _args[_args.index("--dep")+1] if "--dep" in _args else r"E:\名称规范系统\旧规范文档"
INPUT_FILE  = _args[_args.index("--input")+1] if "--input" in _args else r"C:\Users\Administrator\Desktop\张伟1(1).xlsx"
OUTPUT_FILE = _args[_args.index("--output")+1] if "--output" in _args else _args[_args.index("--out")+1] if "--out" in _args else r"E:\名称规范系统\新规范文档系统\matched_papers_v2.xlsx"
PROXY = "http://localhost:3456"

sys.path.insert(0, DEP_PATH)
from author_agent.cnki_api import ensure_cnki_tab

# 内联搜索（补全所有必要字段，不依赖页面状态）
SEARCH_JS = r"""
(function() {
    var base = {
        Platform: "", Resource: "CROSSDB", Classid: "WD0FTY92",
        Products: "CJFQ,CAPJ,ZHYX,CJTL,CDFD,CMFD,CPFD,IPFD,CPVD,CCND,WBFD,SCSF,SCHF,SCSD,SNAD,CCJD,CJFN,CCVD",
        QNode: { QGroup: [{ Key: "Subject", Title: "", Logic: 0, Items: [], ChildItems: [] }] },
        ExScope: "1,2,3,4,5,6,7,8", SearchType: 3, Rlang: "CHINESE",
        KuaKuCode: "YSTT4HG0,LSTPFY1C,JUP3MUPD,MPMFIG1A,EMRPGLPA,WQ0UVIAA,BLZOG7CK,PWFIRAGL,NN3FJMUV,NLBO1Z6R",
        Expands: {}
    };
    base.QNode.QGroup[0].ChildItems = [
        { Key: "a", Title: "", Logic: 0,
          Items: [{ Key: "a", Title: "", Logic: 0, Field: "AU", Operator: "DEFAULT", Value: "{author}", Value2: "" }],
          ChildItems: [] },
        { Key: "a", Title: "", Logic: 0,
          Items: [{ Key: "a", Title: "", Logic: 0, Field: "AF", Operator: "FUZZY", Value: "{institution}", Value2: "" }],
          ChildItems: [] }
    ];
    var qj = JSON.stringify(base);
    var x = new XMLHttpRequest();
    x.open("POST", "/kns8s/brief/grid", false);
    x.setRequestHeader("Content-Type", "application/x-www-form-urlencoded;charset=UTF-8");
    x.send("boolSearch=true&QueryJson=" + encodeURIComponent(qj));
    return x.responseText;
})()
"""

def search_cnki(tab_id, author, institution=""):
    """搜索知网，返回 {count, titles, resultHtml, htmlLength}"""
    js = SEARCH_JS.replace("{author}", author).replace("{institution}", institution or "")
    html = str(eval_js(tab_id, js))
    count_m = re.search(r'共找到</span>\s*<em>(\d+)</em>', html)
    count = count_m.group(1) if count_m else '0'
    titles = []
    for m in re.finditer(r'<a[^>]*class="fz14"[^>]*>([^<]+)</a>', html):
        t = m.group(1).strip()
        if t not in ('题名', '作者', '来源', '发表时间', '数据库', '被引', '下载', '操作') and len(t) > 3:
            titles.append(t)
    return {"count": count, "titles": titles[:20], "resultHtml": html, "htmlLength": len(html)}
from author_agent.cdp_client import eval_js as _eval_js, close_tab, page_text, navigate, wait_for_load

def get(path, retries=5):
    for i in range(retries):
        try:
            with urllib.request.urlopen(PROXY + path, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            if i < retries - 1: time.sleep(3)
            else: raise

def eval_js(tab_id, js, retries=5):
    for i in range(retries):
        try: return _eval_js(tab_id, js)
        except Exception as e:
            if i < retries - 1: time.sleep(2)
            else: raise

def extract_abstract(tab_id, detail_url):
    """在主标签页中导航到摘要页，提取论文信息+作者简介"""
    full = "https://kns.cnki.net" + detail_url.replace("&amp;","&")
    try:
        navigate(tab_id, full)
        time.sleep(2.5)
        wait_for_load(tab_id)
        txt = page_text(tab_id)
    except Exception as e:
        print(f"        abstract error: {e}")
        return None
    if not txt or len(txt) < 100: return None

    info = {"title":"","authors":"","institution":"","abstract":"","year":"","full_institution":"","bio":""}
    idx_zw = txt.find("张伟")
    if idx_zw == -1: return info

    after = txt[idx_zw+2:idx_zw+20]
    sup_m = re.search(r'([\d①②③④⑤⑥⑦⑧⑨,，]+)', after)
    sup_nums = []
    if sup_m:
        circ = {'①':'1','②':'2','③':'3','④':'4','⑤':'5','⑥':'6','⑦':'7','⑧':'8','⑨':'9'}
        for ch in sup_m.group(1):
            if ch.isdigit(): sup_nums.append(ch)
            elif ch in circ: sup_nums.append(circ[ch])

    before = txt[:idx_zw]; line_start = before.rfind('\n') + 1 if '\n' in before else 0
    line_end = txt.find('\n', idx_zw)
    if line_end < 0: line_end = min(len(txt), idx_zw+300)
    info["authors"] = txt[line_start:line_end].strip()[:300]

    inst_line = ""
    for line in txt[line_end:line_end+600].split('\n'):
        ls = line.strip()
        if re.search(r'\d[\.\s]', ls) and any(kw in ls for kw in ['大学','学院','医院','中心','公司','研究所','集团','科室','中学','小学']):
            inst_line = ls; break

    info["full_institution"] = inst_line[:500] if inst_line else ""
    if inst_line:
        inst_parts = re.findall(r'(\d)[\.\s、]?\s*([^\d]{4,80}?(?:大学|学院|医院|研究院|研究所|中心|公司|集团|科室|系|部|处|局|所|委|会|中学|小学))', inst_line)
        inst_map = {num: name.strip() for num, name in inst_parts}
        matched = [inst_map[n] for n in sup_nums if n in inst_map]
        info["institution"] = "; ".join(matched) if matched else inst_line[:300]

    if not info["institution"]:
        ctx = txt[max(0,idx_zw-50):idx_zw+400]
        fallback_insts = re.findall(r'(?:[^\s,;，；]{2,30}(?:大学|学院|医院|研究院|研究所|中心|公司|集团|中学|小学|科室|系))', ctx)
        if fallback_insts:
            info["institution"] = "; ".join(fallback_insts[:5])[:300]

    abs_m = re.search(r'(?:中文\s*)?摘要[：:]\s*([\s\S]+?)(?:关键词|Key\s*words|Abstract|基金|收稿|$)', txt)
    if not abs_m: abs_m = re.search(r'摘要[：:]\s*([\s\S]+?)(?:关键词|Key\s*words|Abstract|基金|收稿|$)', txt)
    if abs_m: info["abstract"] = abs_m.group(1).strip()[:500]

    yr_m = re.search(r'发表时间[：:\s]*(\d{4})', txt)
    if not yr_m: yr_m = re.search(r'\.\s*(\d{4})\s*[,，]', txt)
    if yr_m: info["year"] = yr_m.group(1)

    # 提取作者简介
    try:
        eval_js(tab_id, "window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
        href = str(eval_js(tab_id, """(function(){
            var l=document.querySelectorAll('a');
            for(var i=0;i<l.length;i++){
                if(l[i].textContent.indexOf('HTML')>-1) return l[i].href||'';
            }
            return '';
        })()"""))
        if href and href.startswith('http'):
            eval_js(tab_id, f"window.location.href = '{href}';")
            time.sleep(5)
            wait_for_load(tab_id)
            eval_js(tab_id, "window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)
            bt = page_text(tab_id)
            if bt:
                if '验证' in bt and len(bt) < 500:
                    info["bio"] = "__CAPTCHA__"
                else:
                    idx = bt.find("作者简介")
                    if idx > -1:
                        info["bio"] = bt[idx:idx+600]
    except Exception as e:
        print(f"        bio error: {e}")

    return info

def save(all_matched):
    df = pd.DataFrame(all_matched)
    for attempt in range(5):
        try:
            df.to_excel(OUTPUT_FILE, index=False)
            return
        except PermissionError:
            if attempt < 4: time.sleep(2)
            else:
                backup = OUTPUT_FILE.replace('.xlsx', f'_backup_{int(time.time())}.xlsx')
                df.to_excel(backup, index=False)

def main(start_idx=0, end_idx=None):
    print("1. Loading profiles...")
    df = pd.read_excel(INPUT_FILE, sheet_name=1)
    profiles = []
    for i, row in df.iterrows():
        inst = row.get("在职单位1")
        if pd.isna(inst) or str(inst) in ("未知","nan",""): continue
        if str(row.get("姓名","")) != "张伟": continue
        profiles.append({
            "控制号": str(row.get("控制号","")),
            "在职单位1": str(inst),
            "生年": str(row.get("生年",""))[:4].strip() if pd.notna(row.get("生年")) else "",
        })
    print(f"   {len(profiles)} profiles (sheet2)")

    if end_idx is None:
        end_idx = len(profiles)
    profiles = profiles[start_idx:end_idx]
    print(f"   Processing profiles [{start_idx}:{end_idx}] = {len(profiles)} profiles")

    all_matched = []
    done_ids = set()
    if os.path.exists(OUTPUT_FILE):
        try:
            existing = pd.read_excel(OUTPUT_FILE)
            all_matched = existing.to_dict('records')
            done_ids = set(existing["控制号"].astype(str))
            print(f"   Loaded {len(all_matched)} existing papers, {len(done_ids)} profiles done")
        except:
            print(f"   Starting fresh")
            all_matched = []

    print("\n2. Setting up CNKI tab...")
    tab = ensure_cnki_tab()
    print(f"   Tab: {tab[:20]}")

    try:
        for pi, profile in enumerate(profiles):
            inst = profile["在职单位1"][:50]
            cid = profile["控制号"]
            if cid in done_ids: continue

            print(f"\n[{pi+1}/{len(profiles)}] {inst}")

            try:
                navigate(tab, "https://kns.cnki.net/kns8s/AdvSearch")
                time.sleep(2)
                wait_for_load(tab)
                result = search_cnki(tab, "张伟", profile["在职单位1"])
                count = int(result.get('count', 0))
                titles = result.get('titles', [])
                html = result.get('resultHtml', '')
                html_len = result.get('htmlLength', len(html))
                print(f"   Found: {count} papers")

                if count == 0:
                    short_inst = profile["在职单位1"]
                    for sep in ['系', '室', '部', '处', '中心']:
                        idx = short_inst.rfind(sep)
                        if idx > 6:
                            short_inst = short_inst[:idx+1]
                            break
                    if short_inst != profile["在职单位1"]:
                        print(f"   降级搜索: {short_inst[:40]}")
                        result2 = search_cnki(tab, "张伟", short_inst)
                        count2 = int(result2.get('count', 0))
                        if count2 > 0:
                            count = count2
                            titles = result2.get('titles', [])
                            html = result2.get('resultHtml', '')
                            print(f"   降级后: {count} papers")
                        else:
                            result2 = search_cnki(tab, "张伟", short_inst.split('系')[0] if '系' in short_inst else short_inst[:8])
                            count2 = int(result2.get('count', 0))
                            if count2 > 0:
                                count = count2
                                titles = result2.get('titles', [])
                                html = result2.get('resultHtml', '')
                                print(f"   二级降级: {count} papers")

                if count == 0:
                    all_matched.append({
                        "控制号": cid, "种子单位": profile["在职单位1"],
                        "种子领域": "", "生年": profile["生年"],
                        "论文标题": "", "论文作者": "", "论文机构": "",
                        "发表年份": "", "摘要": "", "论文链接": "", "作者简介": "",
                    })
                    save(all_matched)
                    continue

                detail_urls = re.findall(r'/kcms2/article/abstract\?v=[^"&\']+', html)
                profile_saved = 0
                for i, (title, url) in enumerate(zip(titles, detail_urls)):
                    if i >= 20: break
                    if i > 0: time.sleep(random.uniform(15, 25))
                    print(f"   [{i+1}] {title[:60]}...")
                    try:
                        info = extract_abstract(tab, url)
                    except Exception as e:
                        print(f"        extract error: {e}")
                        continue
                    if not info: continue

                    seed_inst = profile["在职单位1"]
                    paper_inst = info.get("institution","")
                    inst_ok = (seed_inst in paper_inst) or (paper_inst in seed_inst)
                    if not inst_ok:
                        seed_parts = re.split(r'[（）()\-、，,;；]', seed_inst)
                        for part in seed_parts:
                            if len(part) >= 6 and part in paper_inst:
                                inst_ok = True; break
                    if not inst_ok:
                        paper_parts = re.split(r'[;；]', paper_inst)
                        for pp in paper_parts:
                            pp = pp.strip()
                            if len(pp) >= 6 and (pp in seed_inst or seed_inst in pp):
                                inst_ok = True; break
                    if not inst_ok:
                        full_inst = info.get("full_institution","")
                        if full_inst:
                            seed_key = re.sub(r'[（）()\s\-、，,;；]', '', seed_inst)
                            full_key = re.sub(r'[（）()\s\-、，,;；]', '', full_inst)
                            inst_ok = (seed_key[-6:] in full_key) or (seed_key[:6] in full_key)
                    if not inst_ok:
                        print(f"        SKIP: seed=[{seed_inst[:40]}] paper=[{paper_inst[:50]}]")
                        continue

                    birth = profile["生年"]; year = info.get("year","")
                    if birth.isdigit() and year.isdigit():
                        age = int(year) - int(birth)
                        if age < 19 or age > 75:
                            print(f"        SKIP: age {age}")
                            continue

                    bio_val = info.get("bio","")
                    if bio_val == "__CAPTCHA__": bio_val = ""
                    row = {
                        "控制号": cid, "种子单位": profile["在职单位1"],
                        "种子领域": "", "生年": birth,
                        "论文标题": title, "论文作者": info.get("authors",""),
                        "论文机构": info.get("institution",""), "发表年份": year,
                        "摘要": info.get("abstract",""),
                        "论文链接": "https://kns.cnki.net" + url.replace("&amp;","&"),
                        "作者简介": bio_val,
                    }
                    all_matched.append(row)
                    profile_saved += 1
                    bio_flag = " +BIO" if bio_val else (" CAPTCHA" if info.get("bio")=="__CAPTCHA__" else "")
                    print(f"        SAVE: inst=[{info.get('institution','')[:50]}] year={year}{bio_flag}")

                if profile_saved == 0 and count > 0:
                    all_matched.append({
                        "控制号": cid, "种子单位": profile["在职单位1"],
                        "种子领域": "", "生年": profile["生年"],
                        "论文标题": "", "论文作者": "", "论文机构": "",
                        "发表年份": "", "摘要": "", "论文链接": "", "作者简介": "",
                    })

                save(all_matched)
                print(f"   -> {profile_saved} papers matched (total: {len(all_matched)})")

            except Exception as e:
                print(f"   PROFILE ERROR: {e}")
                traceback.print_exc()
                save(all_matched)

            time.sleep(random.uniform(1, 2))

    except KeyboardInterrupt:
        print("\nInterrupted. Saving...")
        save(all_matched)
    except Exception as e:
        print(f"\nFATAL: {e}")
        traceback.print_exc()
        save(all_matched)

    print(f"\nDone! {len(all_matched)} rows saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    args = sys.argv[1:]
    start = int(args[args.index("--start")+1]) if "--start" in args else 0
    end = int(args[args.index("--end")+1]) if "--end" in args else None
    main(start_idx=start, end_idx=end)
