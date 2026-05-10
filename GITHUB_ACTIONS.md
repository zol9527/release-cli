# 🚀 GitHub Actions 发布指南

> 本项目使用 GitHub Actions 将构建产物（`.tar.gz` / `.whl`）上传到 **GitHub Release**，以便在私有仓库中安全分发，无需将包暴露到公开注册表。

## 📋 发布流程

### **方式 1：创建 GitHub Release（推荐）**

```bash
# 1. 更新版本号
uv version --bump patch  # 或 minor / major

# 2. 提交更改
git add pyproject.toml uv.lock
git commit -m "⬆️ bump version to $(uv version --short)"

# 3. 创建 tag
git tag v$(uv version --short)

# 4. 推送
git push origin main --tags

# 5. 在 GitHub 创建 Release
# 访问：https://github.com/zol9527/release-cli/releases/new
# 选择刚推送的 tag，填写 release notes
# 发布后自动触发 publish workflow，包会上传到 GitHub Release
```

---

### **方式 2：推送 Tag**

```bash
# 1. 更新版本
uv version --bump patch

# 2. 提交并打 tag
git add .
git commit -m "⬆️ bump version"
git tag v$(uv version --short)

# 3. 推送 tag（自动触发发布）
git push origin v$(uv version --short)
```

---

### **方式 3：手动触发**

```bash
# 1. 访问 Actions 页面
# https://github.com/zol9527/release-cli/actions/workflows/publish.yml

# 2. 点击 "Run workflow"
# 3. 选择分支并填写 version（例如 v0.1.0）
# 4. 点击 "Run workflow" 按钮
```

---

### **方式 4：本地构建**

```bash
make publish
```

> 本地 `make publish` 仅构建包，正式发布请推送 tag 触发 GitHub Actions。

---

## 📦 发布后的包地址

```
https://github.com/zol9527/release-cli/releases
```

### 安装已发布的包

由于本项目为私有仓库，可从 GitHub Release 下载包并本地安装：

```bash
# 从 Release 页面下载 .whl 文件后安装
pip install release_cli-<version>-py3-none-any.whl

# 或直接使用 pip 从 URL 安装（需要有仓库访问权限）
pip install https://github.com/zol9527/release-cli/releases/download/v<version>/release_cli-<version>-py3-none-any.whl
```

---

## 🔧 Workflow 触发条件

### **自动触发：**
1. ✅ 创建 GitHub Release
2. ✅ 推送 tag（格式：`v*.*.*`）

### **手动触发：**
3. ✅ GitHub Actions 页面手动运行

---

## 📊 发布流程图

```
┌─────────────────┐
│  更新版本号      │
│  uv version │
└────────┬────────┘
         │
         v
┌─────────────────┐
│  提交代码        │
│  git commit     │
└────────┬────────┘
         │
         v
┌─────────────────┐
│  创建 tag        │
│  git tag v0.1.0 │
└────────┬────────┘
         │
         v
┌─────────────────┐
│  推送到 GitHub   │
│  git push --tags│
└────────┬────────┘
         │
         v
┌─────────────────┐
│  GitHub Actions │
│  构建 + 上传到   │
│  GitHub Release │
└─────────────────┘
```

---

## 🎯 完整发布示例

### **发布 0.1.0 版本**

```bash
# 1. 确保在 main 分支
git checkout main

# 2. 拉取最新代码
git pull origin main

# 3. 更新版本号
uv version 0.1.0

# 4. 提交
git add pyproject.toml uv.lock
git commit -m "🚀 release: v0.1.0"

# 5. 打 tag
git tag v0.1.0

# 6. 推送
git push origin main --tags

# 7. 等待 GitHub Actions 自动发布到 GitHub Release
# 查看进度：https://github.com/zol9527/release-cli/actions
# 发布后访问：https://github.com/zol9527/release-cli/releases
```

---

### **发布 0.2.0 版本（有新功能）**

```bash
# 1. 开发新功能...

# 2. 测试
uv run pytest  # 如果有测试

# 3. 更新版本（minor）
uv version --bump minor  # 0.1.0 → 0.2.0

# 4. 提交
git add .
git commit -m "✨ feat: 添加新功能"

# 5. 打 tag
git tag v0.2.0

# 6. 推送
git push origin main --tags
```

---

### **紧急修复（patch）**

```bash
# 1. 修复 bug
# ... 修改代码 ...

# 2. 更新版本（patch）
uv version --bump patch  # 0.2.0 → 0.2.1

# 3. 提交并推送
git add .
git commit -m "🐛 fix: 修复 xxx 问题"
git tag v0.2.1
git push origin main --tags
```

---

## 🔐 权限说明

### **Workflow 需要的权限：**

```yaml
permissions:
  contents: write  # 检出代码 + 创建 GitHub Release
  packages: write  # 上传包到 GitHub Release
```

### **GITHUB_TOKEN：**
- ✅ GitHub Actions 自动提供，无需额外配置
- ✅ 只要 workflow 有 `contents: write` 权限即可创建 GitHub Release
- ✅ 私有仓库下，只有有仓库访问权限的用户可以下载 Release 包

### **本地构建：**
- 运行 `make publish` 仅构建包，不发布
- 正式发布请推送 tag 触发 GitHub Actions

---

## ⚠️ 常见问题

### **Q1: 发布失败，提示权限不足？**

**A:** 检查仓库 Actions 权限设置：
1. Settings → Actions → General
2. Workflow permissions → Read and write permissions
3. 确认当前 workflow 拥有 `contents: write`

---

### **Q2: 版本已存在错误？**

**A:** GitHub Release 不允许重复同一 tag，请先删除旧的 Release 和 tag 或使用新版本号
```bash
# 更新版本号
uv version --bump patch

# 重新发布
git add pyproject.toml
git commit -m "⬆️ bump version"
git tag v$(uv version --short)
git push origin main --tags
```

---

### **Q3: 如何查看发布状态？**

**A:** 访问 Actions 页面
```
https://github.com/zol9527/release-cli/actions
```

---

### **Q4: 如何安装已发布的包？**

**A:** 从 GitHub Release 下载 `.whl` 文件后安装
```bash
# 下载并安装（需要有仓库访问权限）
pip install https://github.com/zol9527/release-cli/releases/download/v<version>/release_cli-<version>-py3-none-any.whl
```

---

## 📈 版本管理策略

### **语义化版本（Semantic Versioning）**

```
MAJOR.MINOR.PATCH

MAJOR - 不兼容的 API 变更
MINOR - 向后兼容的新功能
PATCH - 向后兼容的 bug 修复
```

### **示例：**

| 变更类型 | 命令 | 版本变化 |
|---------|------|---------|
| Bug 修复 | `uv version --bump patch` | 0.1.0 → 0.1.1 |
| 新功能 | `uv version --bump minor` | 0.1.1 → 0.2.0 |
| 重大变更 | `uv version --bump major` | 0.2.0 → 1.0.0 |

---

## ✅ 发布检查清单

**发布前：**
- [ ] 代码已测试
- [ ] 文档已更新
- [ ] CHANGELOG 已更新（如果有）
- [ ] 版本号已更新
- [ ] 所有更改已提交

**发布时：**
- [ ] Tag 已创建
- [ ] Tag 已推送到 GitHub

**发布后：**
- [ ] GitHub Actions 成功运行
- [ ] GitHub Release 页面可见新版本和附件
- [ ] 安装测试成功（从 Release 页面下载 `.whl` 安装）

---

## 🎁 自动化脚本（可选）

创建 `scripts/release.sh`：

```bash
#!/bin/bash
set -e

VERSION_TYPE=${1:-patch}

# 更新版本
uv version --bump $VERSION_TYPE
NEW_VERSION=$(uv version --short)

# 提交
git add pyproject.toml uv.lock
git commit -m "🚀 release: v${NEW_VERSION}"

# 打 tag
git tag v${NEW_VERSION}

# 推送
git push origin main --tags

echo "✅ 发布 v${NEW_VERSION} 成功！"
echo "⏳ 等待 GitHub Actions 上传到 GitHub Release..."
echo "📦 https://github.com/zol9527/release-cli/releases"
```

使用：
```bash
chmod +x scripts/release.sh
./scripts/release.sh patch  # 或 minor / major
```

---

## 🔗 相关链接

- **Workflow 文件：** `.github/workflows/publish.yml`
- **Actions 页面：** https://github.com/zol9527/release-cli/actions
- **Releases 页面：** https://github.com/zol9527/release-cli/releases

---

**Happy Releasing! 🚀**
