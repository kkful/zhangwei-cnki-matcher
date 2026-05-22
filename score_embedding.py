"""使用 Sentence-BERT 嵌入模型计算画像-论文相似度

算法：
  1. Profile文本: "机构：XXX。研究领域：YYY。生年：ZZZZ。"
  2. Paper文本:  "机构：XXX。论文：标题。摘要：..."
  3. Sentence-BERT编码为向量 → 余弦相似度 (50%)
  4. 机构名最长公共子序列 LCS (30%)
  5. 年代合理性 (20%)
  6. 加权综合得分 + 判定

依赖: E:\dedup-env (sentence-transformers, torch, scipy)
用法: python score_embedding.py
"""
import os, sys

# Generate and run embedding script with dedup-env Python
SYS_PYTHON = r"E:\dedup-env\python.exe"

INPUT = r"E:\名称规范系统\新规范文档系统\matched_papers_full.xlsx"
OUTPUT = r"E:\名称规范系统\新规范文档系统\matched_papers_final.xlsx"

# If input doesn't exist, use the full version
if not os.path.exists(INPUT):
    print("Run pipeline.py first to generate matched_papers_full.xlsx")
    sys.exit(1)

SCRIPT = r'''
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import pandas as pd, numpy as np, json, time, difflib, re
from sentence_transformers import SentenceTransformer
from scipy.spatial.distance import cdist

INPUT = r"__INPUT__"
OUTPUT = r"__OUTPUT__"
SHEET1 = r"C:\Users\Administrator\Desktop\张伟1.xlsx"

print("Loading model...")
model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

print("Loading data...")
df = pd.read_excel(INPUT)

# Load sheet1 to get 活动领域 per profile
df1 = pd.read_excel(SHEET1, sheet_name=0)
domain_map = {}
for _, row in df1.iterrows():
    cid = str(row.get("控制号",""))
    if pd.notna(row.get("活动领域")):
        domain_map[cid] = str(row.get("活动领域"))

print(f"  Loaded {len(domain_map)} profiles with domain info")
print(f"  {len(df)} rows in paper data")

def build_text(row):
    parts = []
    inst = str(row.get("种子单位",""))
    if inst: parts.append(f"机构：{inst}")
    birth = str(row.get("生年",""))
    if birth and birth != "nan": parts.append(f"生年：{birth}")
    title = str(row.get("论文标题",""))
    if title and title != "nan": parts.append(f"论文：{title}")
    abstract = str(row.get("摘要",""))
    if abstract and abstract != "nan": parts.append(f"摘要：{abstract[:300]}")
    return "。".join(parts)

profiles = {}
for _, row in df.iterrows():
    cid = str(row["控制号"])
    if cid not in profiles:
        seed_inst = str(row.get("种子单位",""))
        birth = str(row.get("生年",""))
        domain = domain_map.get(cid, "")
        text = f"机构：{seed_inst}。"
        if domain and domain != "nan" and domain != "未知":
            text += f"研究领域：{domain}。"
        if birth and birth != "nan":
            text += f"生年：{birth}。"
        profiles[cid] = text

texts_profile = []
texts_paper = []
for _, row in df.iterrows():
    cid = str(row["控制号"])
    texts_profile.append(profiles.get(cid, ""))
    texts_paper.append(build_text(row))

print(f"Encoding {len(texts_profile)} texts...")
t0 = time.time()
emb_profile = model.encode(texts_profile, batch_size=32, show_progress_bar=True)
emb_paper = model.encode(texts_paper, batch_size=32, show_progress_bar=True)
print(f"  {time.time()-t0:.1f}s")

print("Computing cosine similarity...")
cos_sim = 1 - cdist(emb_profile, emb_paper, metric="cosine")
diag_sim = np.diag(cos_sim)

def normalize(s):
    if not s: return ""
    return re.sub(r"[\s\-()（）]","",str(s))

def lcs_score(s1, s2):
    if not s1 or not s2: return 0.5
    matcher = difflib.SequenceMatcher(lambda c: c.isspace(), s1, s2)
    matchs = matcher.get_matching_blocks()
    matched_len = sum(m.size for m in matchs if m.size > 0)
    return matched_len / min(len(s1), len(s2))

lcs_scores = []
year_scores = []
for _, row in df.iterrows():
    seed_inst = normalize(row.get("种子单位",""))
    paper_inst = normalize(row.get("论文机构",""))
    lcs_scores.append(lcs_score(seed_inst, paper_inst))

    birth = str(row.get("生年","")); year = str(row.get("发表年份",""))
    ys = 0.5
    try:
        by = int(birth[:4].replace("?","").strip())
        py = int(year[:4].strip())
        if by > 1900 and py > 1900:
            age = py - by
            if 25 <= age <= 55: ys = 1.0
            elif 19 <= age <= 75: ys = 0.7
            elif age < 19 or age > 75: ys = 0.1
    except: pass
    year_scores.append(ys)

has_paper_list = [(str(t) != "" and str(t) != "nan") for t in df["论文标题"]]

final_scores = []
for i in range(len(diag_sim)):
    title = str(df.iloc[i].get("论文标题",""))
    if not title or title == "nan":
        final_scores.append(0.0)
    else:
        s = 0.5 * diag_sim[i] + 0.3 * lcs_scores[i] + 0.2 * year_scores[i]
        final_scores.append(round(s, 3))

df["嵌入相似度"] = [round(s, 3) if hp else 0.0 for s, hp in zip(diag_sim, has_paper_list)]
df["机构LCS得分"] = [round(s, 3) if hp else 0.0 for s, hp in zip(lcs_scores, has_paper_list)]
df["年代得分"] = [round(s, 3) if hp else 0.0 for s, hp in zip(year_scores, has_paper_list)]
df["综合得分"] = final_scores

def verdict(s, has_paper):
    if not has_paper: return "无匹配论文"
    if s >= 0.6: return "高置信度"
    if s >= 0.45: return "中置信度"
    if s >= 0.3: return "低置信度"
    return "存疑"

df["判定"] = [verdict(s, hp) for s, hp in zip(final_scores, has_paper_list)]

with_paper = df[df["综合得分"] > 0]
no_paper_count = (df["综合得分"] == 0).sum()
print(f"\n=== Score Distribution (excluding {no_paper_count} rows with no paper) ===")
for label, lo, hi in [("高(>=0.6)",0.6,1), ("中(0.45-0.6)",0.45,0.6), ("低(0.3-0.45)",0.3,0.45), ("存疑(<0.3)",0,0.3)]:
    cnt = ((with_paper["综合得分"] >= lo) & (with_paper["综合得分"] < hi)).sum() if hi < 1 else (with_paper["综合得分"] >= lo).sum()
    print(f"  {label}: {cnt}")

df.to_excel(OUTPUT, index=False)
print(f"\nSaved to: {OUTPUT}")
'''.replace("__INPUT__", INPUT).replace("__OUTPUT__", OUTPUT)

# Write and run
script_path = os.path.join(os.path.dirname(__file__), "_run_embedding.py")
with open(script_path, "w", encoding="utf-8") as f:
    f.write(SCRIPT)

import subprocess
subprocess.run([SYS_PYTHON, script_path], check=True)
