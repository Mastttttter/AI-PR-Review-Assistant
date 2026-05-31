# AI PR Review Assistant

基于大语言模型的自动化 Pull Request 代码审查助手。

## 项目概述

AI PR Review Assistant 能够自动分析 PR 的标题、描述和代码变更，生成结构化的审查报告，包含风险等级、问题列表和修改建议。支持通过规则配置自定义审查策略，支持 OpenAI 和 Anthropic 两种 API 协议，内置 API 分发器实现密钥的安全管理与轮换。

### 核心功能

- **PR 审查**：提交 PR 信息与 diff，自动生成包含摘要、风险评级、问题列表的审查报告
- **规则配置**：自定义审查规则（测试、风格、安全、文档、命名、模块等类型），LLM 智能判断规则匹配
- **助手设置**：配置 OpenAI / Anthropic 提供商，支持 Mock 模式与真实 API，内置连接测试
- **API 分发器**：基于 CLIProxyAPI SDK 的密钥中转服务，签发 10 分钟临时密钥，支持密钥轮换
- **PR 链接解析**：粘贴 GitHub PR URL 自动填充表单
- **反馈系统**：对审查问题进行有用/无用/误报/已采纳/暂不处理标记

---

## [演示视频](https://your-link-here)

系统功能演示与操作流程说明，上传至可访问的外部平台（B站/云盘等）。

---

## 设计思路

### 模型选择

系统支持 **双提供商架构**——同时配置 OpenAI 和 Anthropic 两种 API 协议，通过 `active_provider` 字段动态切换。

- **OpenAI 兼容协议**：支持 OpenAI 官方、DeepSeek 及任何兼容 `/v1/chat/completions` 端点的服务
- **Anthropic 兼容协议**：支持 Anthropic 官方、DeepSeek Anthropic 端点及任何兼容 `/v1/messages` 端点的服务
- **Mock 模式**：内置 MockLLM 提供者，无需真实 API Key 即可运行完整审查流程，适合演示和测试
- **动态切换**：在"助手设置"页面一键切换 Mock/真实 API 模式及当前使用的提供商，无需重启服务

模型选择的设计遵循"抽象适配器"模式：`LLMProvider` 抽象基类定义统一的 `generate_review(prompt)` 接口，`OpenAICompatibleProvider` 和 `AnthropicLLMProvider` 分别实现各自的请求格式和响应解析逻辑，`create_llm_provider()` 工厂函数根据配置动态实例化对应的提供者。

### 上下文获取方式

系统通过多维度信息构建审查上下文，确保 LLM 获得足够信息进行准确判断：

1. **PR 元数据**：标题、描述、项目名称、目标分支、开发者——提供审查的业务背景
2. **代码变更（Diff）**：支持统一 diff 格式和纯代码片段（最大 50,000 字符），自动解析文件路径、行号、变更类型
3. **审查规则**：用户定义的规则（支持 test / style / security / documentation / naming / module 六种类型）以 JSON 格式注入 Prompt，LLM 自主判断规则是否命中
4. **预匹配检测**：基于正则的硬编码模式检测（console.log、debugger、硬编码密钥等）作为上下文提示提供给 LLM
5. **系统提示词**：可自定义的系统级指令，在"助手设置"页面配置并持久化到 `config.json`

Prompt 构建采用分层结构：`系统提示词 → 代码变更上下文 → 团队规则 → 预匹配提示 → JSON 输出格式约束`，确保 LLM 输出结构化、可校验的审查结果。

### 未来扩展方向

- **更多 Git 平台支持**：扩展 PR 链接解析支持 GitLab、Gitee、Bitbucket 等多平台
- **审查历史分析**：基于历史审查数据生成团队代码质量趋势报告，识别高频问题
- **Webhook 集成**：与 GitHub/GitLab Webhook 集成，PR 提交时自动触发审查并回复评论
- **多模型对比**：同一 PR 使用多个模型并行审查，聚合结果提高准确率
- **审查模板**：预设不同场景的审查模板（安全审查、性能审查、代码规范审查）
- **IDE 插件**：提供 VS Code / JetBrains 插件，在编辑器内直接查看审查建议
- **企业级认证**：从 Demo Owner 模式升级为完整的多用户认证与权限管理
- **向量知识库**：结合团队代码库构建向量索引，审查时可参考项目特定上下文

---

## 环境要求

| 组件 | 版本要求 |
|------|---------|
| Python | >= 3.12 |
| Node.js | >= 18 |
| pnpm | 最新版 |
| Go | >= 1.24 |
| Redis | >= 7 |
| Docker | 可选（用于部署分发器） |
| uv | 最新版（Python 包管理器） |

---

## 项目结构

```
├── frontend/          # React TypeScript 前端
│   ├── src/
│   │   ├── api/       # API 客户端、类型定义、标签映射
│   │   ├── App.tsx    # 单文件应用（所有页面组件）
│   │   └── styles.css # 全局样式
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── backend/           # Python FastAPI 后端
│   ├── apr_backend/
│   │   ├── api/       # API 路由（review_tasks, rules, settings, metrics, pr_fetch）
│   │   ├── core/      # 配置加载、认证中间件、日志
│   │   ├── db/        # 数据库模型、枚举、会话管理
│   │   ├── services/  # 业务逻辑（LLM 适配器、编排器、规则引擎、diff 解析）
│   │   └── worker/    # RQ 异步任务（任务队列、消费入口）
│   ├── tests/
│   └── pyproject.toml
├── dispatcher/        # Go 语言 API 分发器（密钥中转服务）
│   ├── main.go        # 服务入口，CLIProxyAPI SDK 集成
│   ├── tempkey/       # 临时密钥管理（自定义访问提供者）
│   ├── config.yaml    # 分发器配置
│   └── go.mod
├── doc/               # 项目文档（PRD、技术文档、前后端任务清单）
├── justfile           # 任务运行器配置
└── docker-compose.yml # Docker 开发环境
```

---

## 快速开始

### 1. 安装依赖

```bash
# 后端
cd backend && uv sync

# 前端
cd frontend && pnpm install
```

### 2. 配置环境变量

复制并编辑 `backend/.env`：

```bash
# LLM 配置
APR_LLM_PROVIDER=openai                    # openai 或 anthropic
APR_LLM_MOCK_ENABLED=true                 # 开发时建议开启 Mock 模式

# 真实 LLM 配置（Mock 关闭时使用）
APR_OPENAI_BASE_URI=https://api.deepseek.com
APR_OPENAI_API_KEY=sk-your-key
APR_OPENAI_MODEL=deepseek-v4-flash
APR_ANTHROPIC_BASE_URI=https://api.deepseek.com/anthropic
APR_ANTHROPIC_API_KEY=sk-your-key
APR_ANTHROPIC_MODEL=deepseek-v4-flash

# 数据库（默认使用 SQLite）
APR_DATABASE_URL=sqlite:///./apr_backend.db

# Redis（RQ 任务队列）
APR_REDIS_URL=redis://localhost:6379/0
```

### 3. 启动服务

```bash
# 启动 Redis
docker start apr-redis-1  # 或 redis-server --daemonize yes

# 启动后端 API
just backend-api          # http://0.0.0.0:8000

# 启动异步 Worker（处理审查任务）
just backend-worker        # 另一个终端

# 启动前端开发服务器
just frontend-dev          # http://127.0.0.1:5173
```

### 4. 配置 API 分发器

> **已部署的分发器**：一个 API 分发器已部署在 **`http://www.ycit.xyz:8318`**，评委可直接在"助手设置"页面中使用。在"从 API 分发器获取凭证"区域输入该地址，点击"获取凭证"即可自动配置。

如需本地部署：

```bash
cd dispatcher
DISPATCHER_LLM_MODEL=deepseek-v4-flash \
DISPATCHER_ANTHROPIC_MODEL=deepseek-v4-flash \
go run .
# 默认监听 http://127.0.0.1:8318
```

分发器 Docker 部署：

```bash
cd dispatcher && bash docker-build.sh
docker run -d --name dispatcher -p 8318:8318 apr-dispatcher:latest
```

---

## 技术架构

### 前端（React + TypeScript + Vite）

单文件组件架构，所有页面定义在 `App.tsx` 中，通过 React Router 进行路由管理。

| 路由 | 页面 | 功能 |
|------|------|------|
| `/` | 工作台 | 仪表盘统计、快捷操作入口 |
| `/reviews/new` | 新建 Review | PR 表单、URI 解析、创建审查 |
| `/reviews/:taskId` | 报告详情 | 审查报告、问题列表、反馈 |
| `/history` | 历史记录 | 任务列表、多维度筛选 |
| `/rules` | 规则配置 | CRUD + 启用/停用 |
| `/settings` | 助手设置 | 提供商配置、系统提示词、分发器集成 |

**技术栈**：React 19、TypeScript、Vite 8、React Router、Vitest

**API 层**：`ApiClient` 类封装所有后端请求，自动进行 camelCase / snake_case 键名转换，统一错误处理。

**测试**：82 个测试（Vitest），覆盖组件渲染、API 调用、用户交互。

### 后端（Python FastAPI + SQLAlchemy + RQ）

**API 模块** (`apr_backend/api/`)：

| 路由 | 功能 |
|------|------|
| `/api/review-tasks` | 审查任务 CRUD、状态查询、PR 信息抓取 |
| `/api/review-rules` | 审查规则 CRUD、启用/停用 |
| `/api/review-issues/:id/feedback` | 问题反馈更新 |
| `/api/settings` | 设置读写、连接测试、分发器凭证获取 |
| `/api/metrics/dashboard` | 仪表盘统计数据 |

**核心服务** (`apr_backend/services/`)：

- `llm_adapter.py` — LLM 提供者抽象层，支持 OpenAI、Anthropic、Mock 三种模式，统一错误类型（`LLMAuthError`、`LLMQuotaExhaustedError`、`LLMTimeoutError`）
- `orchestrator.py` — 审查编排器，负责构建提示词、调用 LLM、验证输出、持久化报告
- `rule_engine.py` — 规则引擎，将规则传递给 LLM 进行智能匹配，支持硬编码模式检测兜底
- `diff_parser.py` — Git diff 解析器，提取文件变更、行号、语言信息
- `ai_validator.py` — AI 输出校验，确保 JSON 结构和枚举值的合法性

**数据库**：SQLite（默认），通过 SQLAlchemy ORM 和 Alembic 迁移管理，核心表：`review_tasks`、`review_reports`、`review_issues`、`review_rules`、`issue_feedback`。

**异步任务**：使用 Redis + RQ 实现异步审查任务队列，Worker 消费 `review` 队列处理 LLM 调用和报告生成。

**配置加载**：`pydantic-settings` 自动从 `.env` 文件和 `APR_` 前缀环境变量加载配置，`config_loader.py` 实现 `config.json` 覆盖 env 的优先级链。

**测试**：330+ 后端测试（pytest）。

### API 分发器（Go + CLIProxyAPI SDK）

基于 CLIProxyAPI v7 SDK 构建的 API 密钥中转服务。

**核心机制**：

1. 分发器内部配置真实的 LLM API 凭证（`config.yaml`）
2. 客户端通过 `/api/issue-key` 获取临时 API Key（10 分钟 TTL）
3. 客户端使用临时 Key 访问分发器的 OpenAI/Anthropic 兼容端点
4. 分发器验证临时 Key 后将请求代理到真实 LLM，返回结果
5. 再次请求 `/api/issue-key` 时，仅清理已过期的旧 Key，有效 Key 保留

**配置示例** (`dispatcher/config.yaml`)：

```yaml
port: 8318
base-uri: "http://your-domain:8318"
api-keys:
  - "static-admin-key"
openai-compatibility:
  - name: "deepseek"
    base-url: "https://api.deepseek.com"
    api-key-entries:
      - api-key: "sk-your-real-api-key"
    models:
      - name: "deepseek-v4-flash"
        alias: "deepseek-v4-flash"
```

**自定义访问提供者** (`dispatcher/tempkey/`)：实现 CLIProxyAPI SDK 的 `sdk/access` 接口，将临时 Key 注入访问管理器，使临时密钥能够通过分发器的认证中间件。

---

## PR 获取流程

```
用户粘贴 GitHub PR URL → 前端调用 /api/pr-fetch
→ 后端解析 owner/repo/pull_number
→ 调用 GitHub API 获取 PR 元数据和 diff
→ 返回 title, description, diff, project, branch, developer
→ 前端自动填充表单
```

---

## 审查流程

```
用户提交审查 → API 创建 ReviewTask → 入队 RQ → Worker 消费
→ 解析 diff → 加载规则 → 构建 Prompt → 调用 LLM
→ 校验输出 → 持久化报告 → 更新任务状态
```

---

## 分发器获取凭证流程

```
用户在设置页输入分发器地址 → 点击获取凭证
→ 后端调用分发器 POST /api/issue-key
→ 分发器生成临时 Key（10 分钟 TTL）并返回
→ 前端自动填充 OpenAI 和 Anthropic 两栏
  （Base URI = 分发器地址，API Key = 临时 Key）
```

---

## 常用命令

```bash
# 后端
just backend-api          # 启动 API 服务器
just backend-worker        # 启动 RQ Worker
just backend-test          # 运行后端测试
just backend-migrate       # 执行数据库迁移

# 前端
just frontend-dev          # 启动开发服务器
just frontend-test         # 运行测试
just frontend-verify       # 类型检查 + 测试 + 构建

# 分发器
cd dispatcher && go run . # 启动分发器
cd dispatcher && go test ./... # 运行测试
```

---

## 环境变量参考

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APR_API_HOST` | `0.0.0.0` | API 监听地址 |
| `APR_API_PORT` | `8000` | API 端口 |
| `APR_DATABASE_URL` | `sqlite:///./apr_backend.db` | 数据库连接 |
| `APR_REDIS_URL` | `redis://localhost:6379/0` | Redis 连接 |
| `APR_LLM_PROVIDER` | `openai` | LLM 提供者 |
| `APR_LLM_MOCK_ENABLED` | `false` | Mock 模式开关 |
| `APR_LLM_TIMEOUT` | `60` | LLM 请求超时（秒） |
| `APR_OPENAI_BASE_URI` | `https://api.openai.com/v1` | OpenAI 兼容 API 地址 |
| `APR_OPENAI_API_KEY` | - | OpenAI API Key |
| `APR_OPENAI_MODEL` | `gpt-4o-mini` | OpenAI 模型名 |
| `APR_ANTHROPIC_BASE_URI` | `https://api.anthropic.com` | Anthropic 兼容 API 地址 |
| `APR_ANTHROPIC_API_KEY` | - | Anthropic API Key |
| `APR_ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Anthropic 模型名 |
| `DISPATCHER_PORT` | `8318` | 分发器端口 |
| `DISPATCHER_LLM_MODEL` | `gpt-4o-mini` | 分发器返回的模型名 |
| `DISPATCHER_KEY_TTL` | `600` | 临时 Key 有效期（秒） |

---

## 许可证

MIT
