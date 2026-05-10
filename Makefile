.PHONY: help install build publish release patch minor major clean test lint

# 默认目标
.DEFAULT_GOAL := help

# GitHub 仓库所有者（可通过命令行覆盖：make publish GITHUB_OWNER=myorg）
GITHUB_OWNER ?= zol9527

# 帮助信息
help: ## 显示帮助信息
	@echo "🚀 Release CLI - 可用命令："
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
	@echo ""

# 安装依赖
install: ## 安装项目依赖
	@echo "📦 安装依赖..."
	poetry install
	@echo "✅ 安装完成！"

# 构建
build: ## 构建分发包
	@echo "🔨 构建包..."
	poetry build
	@echo "✅ 构建完成！"
	@ls -lh dist/

# 构建并输出包（发布由 GitHub Actions 通过 GitHub Release 完成）
publish: build ## 构建包（正式发布请推送 tag 触发 GitHub Actions）
	@echo "✅ 包已构建完成，请推送 tag 触发 GitHub Actions 自动发布到 GitHub Release："
	@echo "   git tag v\$$(poetry version -s) && git push origin dev --tags"
	@echo "📦 https://github.com/$(GITHUB_OWNER)/release-cli/releases"

# 通用发布函数
_release:
	@echo "🚀 发布新版本 ($(VERSION_TYPE))..."
	@poetry version $(VERSION_TYPE)
	@NEW_VERSION=$$(poetry version -s); \
	echo "📌 版本: v$$NEW_VERSION"; \
	git add pyproject.toml poetry.lock; \
	git commit -m "🚀 release: v$$NEW_VERSION"; \
	git tag v$$NEW_VERSION; \
	echo "✅ 准备完成！"; \
	echo ""; \
	echo "下一步："; \
	echo "  git push origin dev --tags"; \
	echo ""; \
	echo "或在 GitHub 创建 Release:"; \
	echo "  https://github.com/zol9527/release-cli/releases/new"

# Patch 版本发布
patch: ## 发布 patch 版本 (0.0.x)
	@$(MAKE) _release VERSION_TYPE=patch

# Minor 版本发布
minor: ## 发布 minor 版本 (0.x.0)
	@$(MAKE) _release VERSION_TYPE=minor

# Major 版本发布
major: ## 发布 major 版本 (x.0.0)
	@$(MAKE) _release VERSION_TYPE=major

# 完整发布流程（包含推送）
release: ## 完整发布流程（版本+提交+tag+推送）
	@echo "🚀 开始完整发布流程..."
	@VERSION_TYPE=$$(git log -1 --pretty=%s | grep -q "feat\|feature" && echo "minor" || echo "patch"); \
	echo "检测到版本类型: $$VERSION_TYPE"; \
	poetry version $$VERSION_TYPE; \
	NEW_VERSION=$$(poetry version -s); \
	echo "📌 版本: v$$NEW_VERSION"; \
	git add pyproject.toml poetry.lock; \
	git commit -m "🚀 release: v$$NEW_VERSION"; \
	git tag v$$NEW_VERSION; \
	git push origin dev --tags; \
	echo "✅ 发布流程完成！"; \
	echo "📦 等待 GitHub Actions 构建..."; \
	echo "🔗 https://github.com/zol9527/release-cli/actions"

# 清理
clean: ## 清理构建文件
	@echo "🧹 清理构建文件..."
	rm -rf dist/ build/ *.egg-info
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -rf .coverage htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ 清理完成！"

# 测试
test: ## 运行测试
	@echo "🧪 运行测试..."
	poetry run pytest -v

# Lint 检查
lint: ## 运行代码检查
	@echo "🔍 运行代码检查..."
	poetry run ruff check .
	poetry run ruff format --check .
	@echo "✅ 检查通过！"

# 类型检查
typecheck: ## 运行类型检查
	@echo "🔍 运行类型检查..."
	poetry run mypy src/
	@echo "✅ 类型检查通过！"

# 开发设置
dev-setup: ## 开发环境设置
	@echo "🔧 设置开发环境..."
	poetry install
	poetry run pre-commit install 2>/dev/null || echo "pre-commit 未安装，跳过"
	@echo "✅ 开发环境设置完成！"

# 查看当前版本
version: ## 查看当前版本
	@poetry version -s

# 更新依赖
update: ## 更新依赖到最新版本
	@echo "⬆️ 更新依赖..."
	poetry update
	@echo "✅ 依赖更新完成！"
