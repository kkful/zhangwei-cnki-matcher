# 张伟名称规范 — 知网定向检索+实体对齐系统

## 背景

"张伟"是中国最常见的姓名之一（超过30万人）。在学术论文数据库中，大量同名作者混杂在一起，导致名称规范记录（Name Authority Record）难以区分。

本系统解决的核心问题：**给定一个已知的张伟画像（姓名+机构+生年），在知网中找到该人发表的所有论文，实现实体对齐与文献富集。**

## 核心思路

### 旧方案（失败）

最初尝试打开知网HTML阅读页面提取"作者简介"栏，但bar.cnki.net有三层防护：
- Referer校验：直接打开→"来源应用不正确"
- Popup拦截：window.open被Chrome阻止
- Session绑定：导航离开后URL全部失效

HTML阅读成功率仅~5%，不可行。

### 新方案（当前）

**种子画像 → 知网作者发文检索 → 详情页角标匹配 → 双向机构校验 → 入库**

```
Excel画像(姓名+机构) 
  → cnki_api(FUZZY模糊搜索) 
  → 开详情页(/kcms2/article/abstract) 
  → 角标提取机构(张伟²→机构2=泰安市中医院) 
  → 双向包含校验(子单位匹配) 
  → 年代过滤(19<年龄<75) 
  → 入库
```

## 技术栈

- **浏览器自动化**: Chrome DevTools Protocol (CDP)，通过web-access skill的CDP Proxy (localhost:3456)
- **知网搜索**: cnki_api模块，使用Operator:FUZZY模糊搜索作者单位
- **页面提取**: CDP page_text + 正则表达式
- **依赖**: Python 3, pandas, openpyxl, Chrome浏览器

## 文件结构

```
├── pipeline.py          # 主流水线脚本
├── cnki_api.py          # 知网搜索API模块（FUZZY+作者发文检索）
├── cdp_client.py        # CDP Proxy客户端封装
├── matched_papers_clean.xlsx  # 输出：885篇匹配论文
├── 张伟1(1).xlsx         # 输入：154个张伟种子画像
└── README.md
```

## 使用方法

### 前置条件

1. Chrome浏览器开启远程调试：`chrome://inspect/#remote-debugging` 勾选"Allow remote debugging"
2. 启动CDP Proxy：
```bash
node "C:/Users/Administrator/.claude/skills/web-access/scripts/check-deps.mjs"
```
3. 安装Python依赖：
```bash
pip install pandas openpyxl
```

### 运行

```bash
python pipeline.py
```

- 从`张伟1(1).xlsx`的sheet2读取154个画像
- 每个画像搜索"张伟+机构"，最多检查20篇论文
- 支持断点续跑（自动跳过已处理的画像）
- 每10个画像存一次checkpoint
- 输出：`matched_papers.xlsx`

### 去重清洗

```bash
python _dedup.py
```

## 核心算法

### 1. 知网搜索（FUZZY模糊匹配）

```javascript
// cnki_api.js 核心逻辑
base.QNode.QGroup[0].ChildItems = [
  {Field: "AU", Operator: "DEFAULT", Value: "张伟"},  // 作者
  {Field: "AF", Operator: "FUZZY", Value: "泰安市中医院"}  // 作者单位(模糊)
];
```

使用`Operator: FUZZY`而非`DEFAULT`，使"泰安市中医院"能匹配到"泰安市中医院消化科"等二级单位。手动搜索找到3篇，FUZZY模式同样找到3篇，而DEFAULT模式只找到1篇。

### 2. 角标机构匹配

知网详情页格式：
```
药学¹张伟²刘鹏³牛彤⁴
1.南京军区总医院消化科 2.泰安市中医院 3.88医院消化科 4.401医院消化科
```

提取逻辑：
1. 找到"张伟"→提取上标数字"²"
2. 解析机构行→`{1: 南京军区总医院, 2: 泰安市中医院, ...}`
3. 用上标数字取对应机构→"泰安市中医院"

这比简单的字符串包含匹配更精确——能区分同一篇论文中多个作者各自的机构，不会把其他作者的机构错配给张伟。

### 3. 双向机构校验

```python
# 处理子单位差异
seed = "云南财经大学区域发展研究所"
paper = "云南财经大学"
# 双向包含: "云南财经大学" ⊂ "云南财经大学区域发展研究所" → 匹配成功
```

支持种子机构名比论文机构名更具体（如带"XX研究所"后缀）或更简略的情况。

### 4. 年代过滤

```python
age = paper_year - birth_year
if age < 19 or age > 75:  # 过滤不可能的情况（14岁发表论文等）
    skip
```

## 输出结果

### 最终数据

| 指标 | 数值 |
|------|------|
| 处理画像数 | 154 |
| 匹配画像数 | 90 |
| 匹配论文数 | 885 |
| 含5篇以上的画像 | 66 |

### Excel字段

| 字段 | 说明 |
|------|------|
| 控制号 | 种子画像唯一标识 |
| 种子单位 | 来自Excel的机构名 |
| 生年 | 出生年份 |
| 论文标题 | 论文题目 |
| 论文作者 | 作者行（含上标数字） |
| 论文机构 | 角标匹配提取的机构 |
| 发表年份 | 论文发表年份 |
| 摘要 | 论文摘要（前500字） |
| 论文链接 | 知网详情页URL |

## 已解决问题与局限

### 已解决
- FUZZY模糊搜索找到更多论文（vs DEFAULT只找到1篇）
- 角标匹配精准定位张伟的机构（非其他作者）
- 双向包含处理子单位名称差异
- 正确拒绝不同机构的同名作者（如：山东中医药大学的张伟 ≠ 泰安市中医院的张伟）
- 断点续跑，进程崩溃不丢数据

### 已知局限
- 部分论文详情页机构提取失败（fallback正则过贪婪，产生19条空机构）
- 64个画像在知网中未找到论文（机构名可能不被CNKI索引）
- 需要Chrome保持运行+CDP连接稳定
- 年代过滤依赖Excel中生年字段的准确性

## 开发历程

1. **V1**: 盲目搜索"张伟"→开HTML阅读页→bar.cnki.net防爬挡死
2. **V2**: XHR搜索+DEFAULT匹配→搜到太少（1篇vs手动3篇）
3. **V3**: FUZZY搜索+角标匹配+双向校验→3篇全命中
4. **V4**: 全量154画像→885篇论文→去重清洗

关键转折点：发现`Operator:FUZZY`和旧的cnki_api.py模块，以及用详情页（/abstract）替代HTML阅读页。