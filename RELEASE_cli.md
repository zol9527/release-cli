# Release CLI

> 当前版本聚焦三件事：初始化配置、通过 Hook 管理版本、按配置打 ZIP 包。

## 命令面

```bash
# 初始化 .release.yml、VERSION、版本 Hook 示例和 GitHub Actions 模板
release-cli init

# 预览下一个版本
release-cli version patch

# 生成明确版本文件，并同步生成 changelog
release-cli version 1.2.3 --write

# 增加本次发布的人工说明并写入 docs/changes/2026-03-11-v1.2.3.md
release-cli version 1.2.3 --write --date 2026-03-11 --title "发布新版本" --note "升级部署步骤"

# 基于当前版本生成发布提交并创建 tag
release-cli commit

# 显式暂存全部改动后再提交
release-cli commit --all

# 根据最新 changelog 的 version 收集文件并生成 zip
release-cli pack
```

`prepare` 仍然保持移除，避免把这个工具继续做成一套耦合的发布编排器。现在生成 changelog 的唯一入口就是 `release-cli version --write`。

`release-cli version` 必须显式传入一个版本参数。允许的输入是 `major`、`minor`、`patch`，或者明确版本号，例如 `1.2.3`。裸调用 `release-cli version` 会直接报参数缺失。

## 版本 Hook

如果你只想维护 `VERSION` 文件：

```yaml
version:
  source: file
  file: VERSION
```

如果你想在写版本后顺带修改 `package.json`、`manifest.json` 或其他文件：

```yaml
version:
  source: file
  hook: .release/_shared/hooks/hook-version.py
```

这里要注意：

1. `source` 只负责决定“当前版本如何读取”，目前是 `file` 或 `git-tag`
2. `hook` 不是版本来源，它只是 `release-cli version --write` 成功后必跑的扩展点
3. 如果你还在用旧配置 `source: script`，需要迁移成 `source: file` 或 `source: git-tag`，再保留 `hook`

脚本约定：

```bash
# release-cli 会把 payload.json 路径作为唯一参数传进来
python .release/_shared/hooks/hook-version.py /tmp/release-hook-payload.json
```

`release-cli init` 会生成一个可直接修改的 `.release/_shared/hooks/hook-version.py` 示例。你只需要在对应同步阶段里补自己的项目逻辑，不需要自己处理命令行输入输出。
默认模板会先同步 `VERSION` 文件，这样无论最终是否要打 tag，发布文件都会先落盘。

## Changelog 与过滤规则

`release-cli version --write` 会默认生成一个固定格式的 Markdown 文件到 `docs/changes` 目录：

```text
docs/changes/2026-03-11-v0.1.0.md
```

这个目录默认相对 `packager.root_dir` 解析，所以即使配置文件放在子目录，生成结果仍然会落到项目根的 `docs/changes`。

固定格式如下：

```md
---
version: "0.1.1"
title: "发布新版本"
releasedAt: "2026-03-08T05:49:07.090Z"
pr: null
prUrl: null
---

## 新增功能

- ✨ feat(admin): 增加用户解锁功能

## 问题修复

- 🛡️ Sentinel: [HIGH] Fix IP Spoofing vulnerability (#150)
```

```yaml
changelog:
  output_dir: docs/changes

filter:
  ignore_messages:
    - "^docs:.*"
    - "^chore:.*"
    - "^style:.*"
    - ".*WIP.*"
    - ".*merge.*"
    - "^Revert.*"
  keep_types:
    - feat
    - fix
    - perf
    - refactor
    - security
```

```bash
# 使用过滤规则生成 changelog
release-cli version 1.2.3 --write --from v1.2.2

# 显示所有提交，不过滤
release-cli version 1.2.3 --write --from v1.2.2 --all

# 添加本次手写说明，可重复传入
release-cli version 1.2.3 --write --note "需要手动迁移旧配置" --note "补充回滚说明"
```

如果你不传 `--from`，默认区间会按 tag 自动推导：

1. 如果当前 HEAD 已经打了 tag，就取“上一个 tag..当前 tag”之间的提交标题
2. 如果当前 HEAD 还没有打 tag，就取“最近 tag..HEAD”之间的提交标题
3. 如果仓库还没有任何 tag，就回退为当前仓库全部提交标题

过滤逻辑保持你之前那套设计：先按 `ignore_messages` 排除，再按 `keep_types` 识别常见 conventional commits 和 emoji commits。

如果某个分类没有内容，这个章节就不会输出。如果你传了 `--note`，这些内容会落到 `## 自定义说明` 章节里。这样生成结果会更接近正式 release notes 的写法。

如果同一天同版本再次生成 changelog，不会再追加 `-2`、`-3` 这种后缀，而是直接覆盖同名版本文件。因为这个文件本质上就是该版本的发布说明，不应该出现多个同版本副本。

如果当前版本源是 `git-tag`，`release-cli version --write` 仍然会以你本次传入的目标版本写入 `VERSION`，并据此命名 changelog。也就是说，生成 changelog 时不再需要额外的独立命令来补版本参数。

如果仓库还没有任何发布 tag，而你一开始就使用 `source: git-tag`，那么显式执行 `release-cli version patch --write` 时，会把首发版本视为当前 `VERSION` 文件中的值；初始化模板默认就是 `v0.1.0`。这样首发流程可以直接在 `git-tag` 模式下完成，不需要先切到 `file`。

## Release Commit

新增了 `release-cli commit`：

```bash
release-cli commit
```

它会读取当前版本，并对当前“已暂存”的内容创建一条固定格式的提交信息：

```text
🔧 chore(release): 准备 v0.1.0 发布文件
```

这里的版本号只会使用 `release-cli version --write` 已经写出的版本文件。所以如果你当前版本是 `1.2.3`，最终提交标题就是 `🔧 chore(release): 准备 v1.2.3 发布文件`。

提交成功后，它还会自动创建对应的 Git Tag，例如 `v1.2.3`。

如果你希望这个命令顺手把所有工作区改动一起暂存，再提交，可以显式传 `--all`。默认不自动 `git add -A`，避免把无关改动混进发布提交。

在真正提交前，`release-cli commit` 还会做发布合理性检查：

1. 版本文件必须存在且能够唯一确定本次发布版本
2. 对应版本的 changelog 文件必须已经存在，且其 frontmatter 中的 `version` 必须和版本文件一致；同时当前版本只能存在唯一一个目标 changelog 文件
3. 上面两个文件必须已经纳入本次提交
4. 目标 Git Tag 不能已经存在

这也意味着，发布参数的选择应该在 `release-cli version --write` 阶段一次性完成；`release-cli commit` 不再接收 `--version` 或 `--date` 之类的人工覆盖参数。

## 打包配置

```yaml
packager:
  root_dir: .
  output_dir: release
  name: "{name}-{version}"
  include:
    - src
    - package.json
    - pyproject.toml
    - VERSION
  exclude:
    - .git
    - .github
    - .beads
    - __pycache__
    - node_modules
```

说明：

1. `include` 支持文件、目录和 glob。
2. `exclude` 会基于项目相对路径过滤，不会把命中的文件写进 zip。
3. 输出始终为 zip，文件名由 `name` 模板和“最新 changelog frontmatter 中的 version”共同决定。
4. 如果配置文件不在项目根目录，把 `packager.root_dir` 调整为正确的项目根，比如 `..`。

执行 `release-cli pack` 前，必须已经通过 `release-cli version --write` 生成过 changelog。命令会从 `docs/changes` 目录中定位最新的 changelog 文件，并读取其 frontmatter 里的 `version` 字段作为最终打包版本。

## 推荐流程

```bash
release-cli init
release-cli version patch
release-cli version patch --write
release-cli commit
release-cli pack
```

现在推荐的职责边界是：`version --write` 生成版本文件并同步产出 changelog，`commit` 统一做提交和打 tag。
