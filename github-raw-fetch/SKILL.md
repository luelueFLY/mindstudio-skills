---
name: github-raw-fetch
description: 当用户提供 GitHub 文件页面链接（尤其是 `github.com/<owner>/<repo>/blob/<ref>/...`）并希望获取 raw content、查看文件原文、抓取源码/配置/Markdown 内容时，使用此技能。技能会自动将普通 GitHub 文件链接转换为 `raw.githubusercontent.com` 链接并获取文件内容。
---

# GitHub Raw Content 获取

## 1. 技能目标

当用户给出 GitHub 文件链接并要求“查看原文”“获取 raw content”“抓取这个文件内容”“读取这个配置/脚本/Markdown”时，快速把标准 GitHub 文件页链接转换成 raw 链接，并获取文件原始内容。

## 2. 适用范围

- 用户提供的是 **GitHub 文件页面链接**，例如：
  - `https://github.com/<owner>/<repo>/blob/<ref>/<path-to-file>`
- 用户提供的是 **已转换好的 raw 链接**，例如：
  - `https://raw.githubusercontent.com/<owner>/<repo>/<ref>/<path-to-file>`
- 目标文件是 README、源码、配置、脚本、JSON、YAML、Markdown 等可直接按文本读取的内容

以下场景不属于本技能的直接处理范围：

- 仓库首页、目录页、Pull Request、Issue、Commit 页面
- 需要递归遍历整个仓库或批量抓取多个文件
- 明显的二进制文件（图片、压缩包、模型权重等）

## 3. 核心转换规则

### 3.1 标准 GitHub 文件页转 raw 链接

如果输入链接满足：

```text
https://github.com/<owner>/<repo>/blob/<ref>/<path-to-file>
```

则转换为：

```text
https://raw.githubusercontent.com/<owner>/<repo>/<ref>/<path-to-file>
```

转换时必须遵守以下规则：

1. 将域名 `github.com` 替换为 `raw.githubusercontent.com`
2. 删除路径中的 `/blob/`
3. 其余路径保持不变
4. 分支、tag、commit SHA 等 `<ref>` 必须原样保留

### 3.2 已是 raw 链接

如果用户提供的本身就是 `raw.githubusercontent.com` 链接，则**不要重复转换**，直接获取内容。

### 3.3 快捷兜底方式

对于标准 GitHub 文件页，也可以尝试在原链接后追加 `?raw=true` 触发重定向；但优先推荐显式转换为 `raw.githubusercontent.com` 链接，结果更直接、稳定。

## 4. 标准操作流程

1. **识别链接类型**
   - 判断是否为 `github.com/.../blob/...` 文件页
   - 或判断是否已是 `raw.githubusercontent.com/...`
2. **生成 raw 链接**
   - 普通 GitHub 文件页按第 3 节规则转换
   - raw 链接则直接使用
3. **获取文件内容**
   - 使用可用的抓取方式请求 raw URL
4. **返回结果**
   - 如果用户只想“看内容”，优先先给摘要或关键片段
   - 如果用户明确要“原文/全文”，则返回原始内容或在平台允许范围内尽量完整展示
   - 必要时附上转换后的 raw URL，便于用户复用

## 5. 示例

### 示例 1：标准 GitHub 文件页

输入：

```text
https://github.com/actioncloud/github-raw-url/blob/master/index.js
```

转换后：

```text
https://raw.githubusercontent.com/actioncloud/github-raw-url/master/index.js
```

### 示例 2：保留 tag / branch / commit

输入：

```text
https://github.com/<owner>/<repo>/blob/v1.2.3/docs/config.md
```

转换后：

```text
https://raw.githubusercontent.com/<owner>/<repo>/v1.2.3/docs/config.md
```

## 6. 错误处理与约束

- 如果链接不是 GitHub 文件页或 raw 文件链接，要明确告知用户该 URL 不符合本技能处理模式
- 如果获取结果返回 404，优先考虑：
  - 路径错误
  - `<ref>` 不存在
  - 仓库或文件为私有资源
- 如果返回的是 HTML 页面而不是文件文本，说明链接可能未正确转换，需重新检查是否遗漏 `/blob/`
- 如果目标内容明显为二进制或体积过大，不要强行按纯文本展开；应告知用户文件类型，并优先返回链接或简要说明

## 7. 输出建议

- 当用户是为了“阅读/分析”文件时，优先提炼关键内容，而不是机械粘贴全文
- 当用户明确要求“raw content”或“原文”时，再按需要返回完整文本
- 在分析代码或配置时，可顺带说明该文件的关键函数、入口、配置项或用途
