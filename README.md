# 张伟名称规范 - 知网论文匹配 + 作者简介提取

基于种子画像（姓名+机构+生年）在知网定向检索论文，自动匹配机构、提取摘要和作者简介。

## 输出

`matched_papers_v2.xlsx`，包含：
- 控制号、种子单位、生年
- 论文标题、论文作者、论文机构、发表年份
- 摘要、论文链接
- **作者简介**（从 HTML 阅读页提取）

## 新电脑搭建（Claude Code 操作）

### 1. 环境准备

```bash
pip install pandas openpyxl numpy opencv-python
pip install ddddocr  # 可选，滑块验证码破解用
```

### 2. Chrome 远程调试

Chrome 地址栏打开 `chrome://inspect/#remote-debugging`，勾选 **"Allow remote debugging for this browser instance"**。

### 3. 启动 CDP Proxy

安装 Claude Code 的 web-access skill，启动 CDP Proxy（端口 3456）。

### 4. 准备输入文件

将 `张伟1(1).xlsx`（含 sheet2 的 154 个张伟画像）放到指定位置。

### 5. 运行

```bash
# 从第96个profile续跑（之前的已完成）
python pipeline.py \
  --dep ./author_agent \
  --input 张伟1(1).xlsx \
  --output matched_papers_v2.xlsx \
  --start 96

# 分批跑（0-6）
python pipeline.py --dep ./author_agent --input 张伟1.xlsx --start 0 --end 6
```

### 6. 中途验证码

bar.cnki.net 会弹拼图验证码，目前 CDP 代理不支持真实鼠标拖拽事件，自动破解不了。**需要人工去 Chrome 手动完成验证码**，完成后程序继续。

建议每 5-6 个 profile 清一次验证码。

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--dep` | author_agent 目录路径 | `E:\名称规范系统\旧规范文档` |
| `--input` | 输入 Excel 文件 | `C:\Users\Administrator\Desktop\张伟1(1).xlsx` |
| `--output` | 输出 Excel 文件 | `E:\名称规范系统\新规范文档系统\matched_papers_v2.xlsx` |
| `--start` | 起始 profile 索引 | 0 |
| `--end` | 结束 profile 索引 | 全部 |

## 文件结构

```
├── pipeline.py           # 主程序
├── slider_solver.py      # 滑块破解（ddddocr + OpenCV）
└── author_agent/
    ├── __init__.py        # 空文件
    ├── cnki_api.py        # 知网搜索 API
    └── cdp_client.py      # CDP 浏览器控制
```

## 原理

1. 在知网高级检索页通过 XHR 调用 `/kns8s/brief/grid` API 搜索「张伟+机构」
2. 逐个打开论文摘要页，提取角标匹配的机构、摘要、年份
3. 如果摘要页有 HTML 阅读入口，通过 `location.href` 跳转 reader 页提取作者简介
4. 每篇论文间隔 15-25 秒防止触发验证码
5. 搜索结果为 0 时自动降级搜索（去掉系/室/部等细节重新搜）
