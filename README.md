# 张伟名称规范 — 知网定向检索+实体对齐系统

## 背景

"张伟"是中国最常见的姓名之一（超过30万人）。在学术论文数据库中，大量同名作者混杂在一起，导致名称规范记录（Name Authority Record）难以区分。

本系统解决的核心问题：**给定一个已知的张伟画像（姓名+机构+领域+生年），在知网中找到该人发表的所有论文，并通过嵌入模型计算相似度，判定是否属于同一个人。**

## 核心流水线

```
Excel画像(姓名+机构+生年) 
  → cnki_api(FUZZY模糊搜索) 
  → 开详情页(/kcms2/article/abstract) 
  → 角标提取机构(张伟²→机构2=泰安市中医院) 
  → 双向包含校验(子单位匹配) 
  → 入库(matched_papers_full.xlsx)
  → Sentence-BERT嵌入评分(机构+领域+生年 vs 论文+摘要)
  → 最终输出(matched_papers_final.xlsx)
```

## 相似度算法

**Sentence-BERT 嵌入 + 最长公共子序列(LCS) + 年代校验**

```
综合得分 = 0.5 × 嵌入余弦相似度 + 0.3 × 机构LCS + 0.2 × 年代得分

Profile文本: "机构：泰安市中医院。研究领域：医学。生年：1966。"
Paper文本:  "机构：泰安市中医院。论文：美沙拉秦...。摘要：溃疡性结肠炎..."

判定: ≥0.6高置信度 | 0.45-0.6中 | 0.3-0.45低 | <0.3存疑 | 0无匹配
```

## 最终结果

| 指标 | 数值 |
|------|------|
| 处理画像数 | 154 |
| 匹配画像数 | 90 |
| 匹配论文数 | 885 |
| 无匹配画像 | 64（空行标0） |

| 判定 | 数量 |
|------|------|
| 高置信度 (≥0.6) | 555 |
| 中置信度 (0.45-0.6) | 296 |
| 低置信度 (0.3-0.45) | 27 |
| 存疑 (<0.3) | 7 |

## 文件结构

```
├── pipeline.py               # 主流水线（搜画像→开摘要→角标匹配→入库）
├── score_embedding.py        # 嵌入评分（Sentence-BERT + LCS + 年代）
├── cnki_api.py               # 知网FUZZY搜索API
├── cdp_client.py             # CDP Proxy浏览器客户端
├── dedup.py                  # 去重清洗脚本
├── requirements.txt          # pandas, openpyxl
└── README.md
```

## 使用方法

### 前置条件

1. Chrome远程调试 + CDP Proxy (localhost:3456)
2. conda环境 `E:\dedup-env`（sentence-transformers, torch）
3. 输入文件：张伟1(1).xlsx (sheet2)

### 运行

```bash
# 第一步：搜画像→匹配论文
python pipeline.py

# 第二步：去重清洗（如断点续跑后需要）
python dedup.py

# 第三步：嵌入评分
python score_embedding.py
```

## 已知局限

- 64个画像在知网中未找到论文（机构名不被CNKI索引）
- 部分论文机构提取失败（~19条空机构）
- 嵌入模型 `paraphrase-multilingual-MiniLM-L12-v2` 对中文支持有限，可升级为 `text2vec-base-chinese`
- 需要Chrome保持运行+CDP连接稳定

## 开发历程

1. **V1**: 盲目搜索"张伟"→开HTML阅读页→bar.cnki.net防爬挡死
2. **V2**: XHR搜索+DEFAULT匹配→搜到太少（1篇vs手动3篇）
3. **V3**: FUZZY搜索+角标匹配+双向校验→3篇全命中
4. **V4**: 全量154画像→885篇论文
5. **V5**: Sentence-BERT嵌入+领域信息→555高置信度