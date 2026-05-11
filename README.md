# Release Pilot

> 面向配置初始化、版本 Hook 和 ZIP 打包的轻量级发布工具

## 安装

```bash
# 方式一：pip 安装
pip install release-cli

# 方式二：使用 uv 开发安装
git clone https://github.com/zol9527/release-cli.git
cd release-cli
uv sync --group dev
uv run release-cli --help
```

## 快速开始

```bash
# 1. 初始化配置和 Hook 示例
release-cli init

# 2. 预览下一个版本
release-cli version patch

# 3. 生成版本文件和 changelog
release-cli version 1.2.3 --write

# 也可以在生成时指定 changelog 标题和自定义说明
release-cli version 1.2.3 --write --title "发布新版本" --note "升级数据库配置"

# 4. 生成发布提交并创建 tag
release-cli commit

# 或者直接执行完整发布流水线
release-cli release patch
release-cli release minor --to-step prepare
release-cli release 1.2.3 --only preflight,prepare

# 或者显式暂存全部变更后再提交
release-cli commit --all

# 5. 直接生成 zip 包，版本来自最新 changelog 的 frontmatter
release-cli pack
```

## 配置

`release-cli init` 生成的文件全部位于 `.release/` 目录。单项目默认配置文件是 `.release/release.yml`：

```yaml
version:
  source: file
  tag_prefix: "v"
  file: _state/VERSION
  hook: _shared/hooks/hook-version.py

changelog:
  output_dir: docs/changes

filter:
  ignore_messages:
    - "^docs:.*"
    - "^chore:.*"
  keep_types:
    - feat
    - fix
    - perf
    - refactor
    - security

packager:
  root_dir: ..
  output_dir: release
  name: "{name}-{version}"
  respect_gitignore: true
  include:
    - "*"
  exclude:
    - .git
    - .github
    - .beads
    - __pycache__
  force_include: []

release:
  steps:
    - preflight
    - prepare
    - commit
    - pr
  allowed_branches:
    - "^dev$"
    - "^hotfix/.+$"
  auto_stage: true
  create_pr: false
  push: false
  base_branch: release

workflow:
  release:
    script: _shared/hooks/hook-release.py
```

如果你希望版本写入后顺手修改 `package.json`、`manifest.json` 等文件，直接编辑 `release-cli init` 生成的 `.release/_shared/hooks/hook-version.py` 即可。这个 hook 在 `source: file` 和 `source: git-tag` 下都可以使用，版本来源仍然只由 `version.source` 决定。

Monorepo 项目可以通过 `version.tag_prefix` 为不同发布单元隔离 Git tag。例如后端使用 `backend/v`，小程序使用 `wechat/v`，同一个仓库里就会生成 `backend/v1.2.3` 和 `wechat/v1.0.1` 两条互不影响的发布线。

如果你之前用的是旧语义 `source: script`，现在需要迁移成：

```yaml
version:
  source: file   # 或 git-tag
  hook: .release/_shared/hooks/hook-version.py
```

Hook 约定如下：

```bash
# release-cli 会把 payload.json 路径作为唯一参数传进去
python .release/_shared/hooks/hook-version.py /tmp/release-hook-payload.json
```

这个 payload 里会包含：
1. `version`: 目标版本
2. `previous_version`: 写入前的版本
3. `version_source`: `file` 或 `git-tag`
4. `project_root`: 项目根目录
5. `config_file`: 当前配置文件路径
6. `version_file`: VERSION 文件路径
7. `git_tag`: 对应的 tag 名，例如 `v1.2.3`

你只需要在 Hook 模板里的 `apply_version_update(context)` 函数中补自己的业务逻辑。
默认模板已经会先同步 `VERSION` 文件，你只需要继续补额外的自定义逻辑。

## 命令

| 命令 | 说明 |
|------|------|
| `release-cli init` | 初始化配置 |
| `release-cli version` | 必须显式传入 major/minor/patch 或明确版本号，用于预览或生成版本文件和 changelog |
| `release-cli commit` | 校验发布文件后生成提交并创建 tag |
| `release-cli release` | 按 preflight/prepare/commit/pr 执行完整发布流水线 |
| `release-cli pack` | 按配置收集文件并打 zip，版本来自最新 changelog |

`release-cli version` 必须显式接收一个版本参数。可用值只有三类：`major`、`minor`、`patch`，或者明确版本号，例如 `1.2.3`。直接执行 `release-cli version` 会报参数缺失错误。

`release-cli version --write` 会按 tag 自动推导 changelog 的提交范围：
1. 如果 HEAD 正好有 tag，就输出“上一个 tag..当前 tag”之间的提交标题
2. 如果 HEAD 没有 tag，就输出“最近 tag..HEAD”之间的提交标题
3. 如果仓库里还没有 tag，就回退为全量提交标题

现在 `release-cli version --write` 会默认生成固定格式的 Markdown 文件到项目根下的 `docs/changes/<日期>-v<版本>.md`。如果同一天同版本再次生成，会直接覆盖这个版本文件，避免出现重复版本的多份记录。

文件内容会使用固定 frontmatter 模板，并按提交类型拆成中文章节，例如 `新增功能`、`问题修复`、`性能优化`。没有内容的章节不会输出。

默认输出仍然会套用 `filter.ignore_messages` 和 `filter.keep_types`。只有传 `release-cli version --write --all` 时才会跳过过滤。你可以通过重复传入 `--note` 为本次发布补充手写说明。

如果当前版本源是 `git-tag`，但 HEAD 还没有落上新的发布 tag，`release-cli version --write` 会直接以这次传入的目标版本写入 `VERSION` 并生成对应 changelog。

如果你从一开始就把 `version.source` 设成 `git-tag`，仓库里又还没有任何发布 tag，那么显式执行 `release-cli version patch --write` 会优先使用现有 `VERSION` 文件里的首发版本；如果还是初始化状态，首发版本默认就是 `v0.1.0`，不需要先切回 `file` 再切回来。

`release-cli version --write` 现在会一次性完成两件事：生成版本文件，以及生成对应的 changelog 文件；但它仍然不负责创建 Git Tag。

`release-cli commit` 只会读取 `release-cli version --write` 已经写出的版本文件和 changelog，校验两者都已生成且已纳入本次提交，然后对“已暂存内容”生成一次标准化提交，标题为 `🔧 chore(release): 准备 vx.x.x 发布文件`，最后再创建对应的 Git Tag。如果你确实要把当前工作区全部变更一起提交，再显式使用 `release-cli commit --all`。

`release-cli commit` 默认还会检查三件事：
1. `VERSION` 文件必须能够唯一确定当前发布版本，且要和 changelog frontmatter 中的 `version` 一致
2. 对应的 `docs/changes/<日期>-v<版本>.md` 是否已经生成，且当前版本只能存在唯一一个目标 changelog 文件
3. 版本文件和 changelog 是否已纳入本次提交，以及目标 tag 是否尚未存在

`release-cli release` 是推荐的一站式发布入口。默认步骤是：

1. `preflight`: 检查 Git、当前分支、工作区状态、目标 tag 是否已存在
2. `prepare`: 等价于 `version <value> --write`，生成 changelog、写入版本文件并执行 `version.hook`
3. `commit`: 自动暂存发布相关文件，创建发布提交和命名空间 tag
4. `pr`: 可选创建发布 PR，默认关闭

流水线支持分段执行：

```bash
release-cli release patch --to-step prepare
release-cli release patch --from-step commit
release-cli release patch --only preflight,prepare
release-cli release patch --skip pr
release-cli release patch --dry-run
```

阶段定制统一写在 `workflow.release.script` 指向的 Python 文件中。模板里的阶段函数可以调用 `ctx.builtin()` 复用内置逻辑；如果省略某个阶段函数，表示该阶段在自定义 workflow 中跳过。

Python workflow 支持清晰的生命周期函数：

```python
def before_all(ctx): ...
def before_step(ctx): ...
def before_prepare(ctx): ...
def prepare(ctx): ...
def after_prepare(ctx): ...
def after_step(ctx): ...
def after_all(ctx): ...
def on_success(ctx): ...
def on_failure(ctx): ...
```

`before_{step}` / `{step}` / `after_{step}` 中的 `step` 对应 `preflight`、`prepare`、`commit`、`pr`。

`release-cli pack` 不再接收版本参数，而是会读取 `docs/changes` 下最新 changelog 的 frontmatter 中的 `version` 字段作为打包版本。如果还没有生成 changelog，命令会直接报错并提示先执行 `release-cli version --write`。

## 文档

详细文档见 [RELEASE_cli.md](RELEASE_cli.md)

## 🚀 GitHub Actions 自动发布

本项目使用 GitHub Actions 自动构建 Python 分发包，并上传到私有 GitHub Release 资产。
只要对仓库有访问权限，就可以在对应 Release 页面下载这些文件。

### 发布方式

**方式 1：创建 GitHub Release（推荐）**
```bash
# 1. 更新版本
make patch  # 或 minor / major

# 2. 推送
git push origin main --tags

# 3. 在 GitHub 创建 Release
# 访问：https://github.com/zol9527/release-cli/releases/new
```

**方式 2：使用 Makefile（快速）**
```bash
# 一键发布
make release
```

### 查看详细文档

- [GitHub Actions 发布指南](GITHUB_ACTIONS.md)
- [Makefile 命令说明](#makefile-命令)

---

## 📦 Makefile 命令

| 命令 | 说明 |
|------|------|
| `make install` | 安装依赖 |
| `make build` | 构建分发包 |
| `make publish TAG=vx.y.z` | 上传 dist 到 GitHub Release |
| `make patch` | 发布 patch 版本 (0.0.x) |
| `make minor` | 发布 minor 版本 (0.x.0) |
| `make major` | 发布 major 版本 (x.0.0) |
| `make release` | 完整发布流程 |
| `make test` | 运行测试 |
| `make lint` | 代码检查 |
| `make clean` | 清理构建文件 |

运行 `make help` 查看所有可用命令。

---

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件
