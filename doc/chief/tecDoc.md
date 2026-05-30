下面给出一份面向 **AI PR Review 助手 MVP v1.0** 的具体技术架构方案。该方案以 PRD 中的核心闭环为边界：创建 Review 任务、输入 PR diff、生成摘要、风险等级、问题列表、修改建议、查看报告、配置规则、历史记录和反馈。PRD 明确说明 MVP 目标不是替代人工 Review，而是在人工 Review 前完成基础 AI 辅助审查，并且暂不支持自动修改代码、自动合并 PR、完整仓库知识库和复杂权限系统，因此架构应保持轻量但可扩展。

# 1. 总体架构结论

推荐采用：

> **前后端分离 + 模块化单体后端 + 异步 AI Review Worker + PostgreSQL + Redis 队列 + LLM API Adapter**

不建议 MVP 阶段直接上微服务。原因是当前产品核心是一次 Review 任务的完整闭环，业务边界清晰，复杂度主要来自 AI 调用、任务状态和结构化报告生成，而不是高并发、多团队、多租户或复杂组织权限。

整体架构如下：

```text
Browser
  │
  ▼
Frontend SPA
React / Vue + TypeScript
  │
  ▼
Backend API
FastAPI / NestJS / Spring Boot
  │
  ├── Review Task Module
  ├── Rule Module
  ├── Report Module
  ├── Feedback Module
  ├── Metrics Module
  └── AI Review Orchestrator
          │
          ▼
      Redis Queue
          │
          ▼
AI Review Worker
  │
  ├── Diff Parser
  ├── Rule Engine
  ├── Prompt Builder
  ├── LLM Adapter
  ├── Result Validator
  └── Report Generator
          │
          ▼
PostgreSQL
```

# 2. 推荐技术选型

## 2.1 前端

推荐：

```text
React + TypeScript + Ant Design + Monaco Editor
```

原因：

| 技术                           | 用途                  |
| ---------------------------- | ------------------- |
| React / Vue                  | 构建单页应用              |
| TypeScript                   | 保证前端数据结构稳定          |
| Ant Design / Element Plus    | 快速实现后台管理类页面         |
| Monaco Editor                | 展示和输入代码 diff        |
| React Query / TanStack Query | 管理接口请求、轮询 Review 状态 |
| ECharts                      | MVP 中展示简单统计卡片       |

页面包括：

```text
首页 / 工作台
新建 Review 页面
Review 报告详情页
Review 规则配置页
历史记录页
```

PRD 中要求报告页包含 PR 基本信息、Review 状态、AI 摘要、风险等级、问题统计、问题列表、修改建议和反馈入口，因此前端重点不是复杂交互，而是结构化展示和状态流转。

## 2.2 后端

推荐：

```text
Python FastAPI + SQLAlchemy + Pydantic
```

原因：

| 技术          | 用途                           |
| ----------- | ---------------------------- |
| FastAPI     | 快速开发 REST API                |
| Pydantic    | 定义 AI 输出 JSON Schema 和接口 DTO |
| SQLAlchemy  | ORM                          |
| Alembic     | 数据库迁移                        |
| Celery / RQ | 异步任务                         |
| Redis       | 任务队列和状态缓存                    |
| PostgreSQL  | 持久化任务、报告、规则、反馈               |

因为 AI Review 涉及 Prompt 构造、JSON 校验、LLM API 调用和异步处理，Python 技术栈实现成本较低。MVP 阶段建议避免使用 C++ 作为主业务后端，除非项目组已经有成熟 C++ Web 工程基础。

## 2.3 AI 模型接入

采用：

```text
LLM Provider Adapter
```

不要把业务代码直接绑定到某一家模型 API，而是抽象一层：

```text
LLMClient
  ├── OpenAICompatibleClient
  ├── LocalModelClient
  └── MockLLMClient
```

这样比赛演示时可以使用线上大模型，开发测试时可以使用 Mock 输出，后续也方便替换模型。

# 3. 后端模块划分

## 3.1 Review Task Module

负责 Review 任务生命周期。

核心职责：

```text
创建 Review 任务
校验 PR 标题和代码 diff
保存任务基础信息
更新任务状态
触发异步 AI Review
查询历史任务
删除任务
重新 Review
```

对应 PRD 的：

```text
创建 Review 任务
输入 PR 变更内容
历史 Review 记录
Review 状态：待分析 / 分析中 / 已完成 / 分析失败 / 已删除
```

## 3.2 AI Review Orchestrator

这是系统核心模块，负责协调一次 AI Review 的完整流程。

```text
AIReviewOrchestrator
  ├── load_task()
  ├── load_enabled_rules()
  ├── parse_diff()
  ├── calculate_change_metrics()
  ├── run_rule_engine()
  ├── build_prompt()
  ├── call_llm()
  ├── validate_llm_result()
  ├── generate_report()
  └── persist_result()
```

注意：Orchestrator 不直接写具体模型逻辑，而是调用 LLM Adapter。

## 3.3 Diff Parser Module

负责把用户输入的 diff 或代码片段转为结构化数据。

输入：

```text
PR 标题
PR 描述
代码 diff
项目名
目标分支
开发者名称
```

输出：

```json
{
  "files": [
    {
      "path": "src/auth/AuthService.ts",
      "language": "typescript",
      "added_lines": 42,
      "deleted_lines": 15,
      "hunks": [
        {
          "old_start": 10,
          "new_start": 10,
          "content": "..."
        }
      ]
    }
  ],
  "metrics": {
    "file_count": 3,
    "added_lines": 120,
    "deleted_lines": 35,
    "contains_test_file": false,
    "sensitive_keywords": ["auth", "token"]
  }
}
```

这一步很重要，因为风险等级评估需要依赖改动规模、模块重要性、复杂度、安全敏感性、测试完整性和规则命中情况。PRD 中明确这些是风险评估维度。

## 3.4 Rule Engine Module

负责处理团队配置的 Review 规则。

规则类型包括：

```text
必须补充测试
禁止提交内容
文档同步要求
安全规则
命名规范
模块约束
```

规则引擎分两层：

```text
硬规则匹配
  例如 console.log、debugger、TODO、敏感关键字、未包含测试文件

AI 语义规则匹配
  例如 Controller 层是否直接操作数据库、接口修改是否需要更新文档
```

MVP 阶段可以先做硬规则 + LLM 辅助解释，不必实现复杂静态分析。

## 3.5 Report Module

负责生成和查询结构化报告。

报告内容：

```text
PR 基本信息
Review 状态
AI 摘要
风险等级
风险原因
问题统计
高 / 中 / 低风险问题列表
规则命中情况
用户反馈状态
```

PRD 要求每个问题包含标题、类型、严重程度、说明、相关代码位置、修改建议和置信度，并且问题应按严重程度排序。

## 3.6 Feedback Module

负责用户对 AI 建议的反馈。

反馈状态：

```text
未反馈
有用
无用
误报
已采纳
暂不处理
```

反馈数据后续可以用于统计建议有用率、误报率、建议采纳率等质量指标。

# 4. AI Review 核心流程

一次 Review 的完整技术流程如下：

```text
1. 用户提交 PR 标题、描述、diff
2. Backend 校验必填项
3. 创建 review_task，状态为 pending
4. 写入数据库
5. 投递 review_job 到 Redis Queue
6. Worker 获取任务
7. 更新状态为 running
8. 解析 diff
9. 加载启用的 Review 规则
10. 执行规则命中检查
11. 构造 AI Prompt
12. 调用 LLM
13. 校验 LLM 输出 JSON
14. 生成结构化报告
15. 写入 review_report 和 review_issues
16. 更新任务状态为 completed
17. 前端轮询或 SSE 获取完成状态
18. 用户查看报告并反馈
```

状态机如下：

```text
pending
  │
  ▼
running
  │
  ├── completed
  │
  └── failed
  │
  ▼
deleted
```

和 PRD 中的任务状态保持一致。

# 5. AI 输出结构设计

AI 不应直接输出自由文本，而应输出严格 JSON。

推荐 Schema：

```json
{
  "summary": {
    "purpose": "string",
    "changed_modules": ["string"],
    "key_files": ["string"],
    "business_impact": "string",
    "test_or_security_notes": "string"
  },
  "risk": {
    "level": "low | medium | high",
    "reasons": ["string"]
  },
  "issues": [
    {
      "title": "string",
      "type": "logic | exception | security | performance | maintainability | test_missing | rule_violation",
      "severity": "low | medium | high",
      "description": "string",
      "location": {
        "file_path": "string",
        "line_hint": "string",
        "code_snippet": "string"
      },
      "suggestion": "string",
      "confidence": "low | medium | high",
      "matched_rule_ids": ["string"]
    }
  ]
}
```

后端必须做二次校验：

```text
字段是否完整
risk.level 是否合法
severity 是否合法
issue 是否包含 suggestion
高 / 中风险问题是否有修改建议
问题是否按严重程度排序
matched_rule_ids 是否存在
```

这样可以满足 PRD 对准确性、可解释性和结构化报告的要求。PRD 特别强调 AI 输出应基于用户代码内容、不确定问题要标明置信度、风险等级和问题都必须解释原因。

# 6. 数据库设计

## 6.1 review_tasks

```sql
CREATE TABLE review_tasks (
    id UUID PRIMARY KEY,
    pr_title VARCHAR(255) NOT NULL,
    pr_description TEXT,
    project_name VARCHAR(255),
    target_branch VARCHAR(255),
    developer_name VARCHAR(255),

    diff_content TEXT NOT NULL,

    status VARCHAR(32) NOT NULL,
    risk_level VARCHAR(32),
    issue_count INT DEFAULT 0,

    created_by UUID,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    deleted_at TIMESTAMP
);
```

## 6.2 review_reports

```sql
CREATE TABLE review_reports (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES review_tasks(id),

    summary TEXT NOT NULL,
    risk_level VARCHAR(32) NOT NULL,
    risk_reasons JSONB NOT NULL,
    issue_stats JSONB NOT NULL,

    raw_ai_result JSONB,
    created_at TIMESTAMP NOT NULL
);
```

## 6.3 review_issues

```sql
CREATE TABLE review_issues (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES review_tasks(id),
    report_id UUID NOT NULL REFERENCES review_reports(id),

    title VARCHAR(255) NOT NULL,
    issue_type VARCHAR(64) NOT NULL,
    severity VARCHAR(32) NOT NULL,
    description TEXT NOT NULL,
    file_path TEXT,
    line_hint TEXT,
    code_snippet TEXT,
    suggestion TEXT NOT NULL,
    confidence VARCHAR(32) NOT NULL,

    matched_rule_ids JSONB,
    feedback_status VARCHAR(32) DEFAULT 'none',

    created_at TIMESTAMP NOT NULL
);
```

## 6.4 review_rules

```sql
CREATE TABLE review_rules (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    rule_type VARCHAR(64) NOT NULL,
    severity VARCHAR(32) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

## 6.5 issue_feedback

```sql
CREATE TABLE issue_feedback (
    id UUID PRIMARY KEY,
    issue_id UUID NOT NULL REFERENCES review_issues(id),
    task_id UUID NOT NULL REFERENCES review_tasks(id),

    feedback_status VARCHAR(32) NOT NULL,
    comment TEXT,

    created_by UUID,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

# 7. API 设计

## Review 任务

```http
POST /api/review-tasks
GET  /api/review-tasks
GET  /api/review-tasks/{task_id}
DELETE /api/review-tasks/{task_id}
POST /api/review-tasks/{task_id}/rerun
```

创建任务请求：

```json
{
  "pr_title": "优化用户登录逻辑",
  "pr_description": "新增 token 刷新机制",
  "project_name": "user-center",
  "target_branch": "main",
  "developer_name": "Alice",
  "diff_content": "diff --git ..."
}
```

创建任务响应：

```json
{
  "task_id": "uuid",
  "status": "pending"
}
```

## Review 报告

```http
GET /api/review-tasks/{task_id}/report
```

## Review 规则

```http
POST   /api/review-rules
GET    /api/review-rules
PUT    /api/review-rules/{rule_id}
PATCH  /api/review-rules/{rule_id}/enable
PATCH  /api/review-rules/{rule_id}/disable
DELETE /api/review-rules/{rule_id}
```

## 用户反馈

```http
PATCH /api/review-issues/{issue_id}/feedback
```

请求：

```json
{
  "feedback_status": "useful | useless | false_positive | adopted | ignored",
  "comment": "这个建议有帮助"
}
```

## PR 抓取

```http
POST /api/pr-fetch
```

请求：

```json
{
  "url": "https://github.com/octocat/hello-world/pull/42"
}
```

响应 `FetchPrResponse`：

```json
{
  "title": "Fix login bug",
  "description": "Fixed the race condition.",
  "diff_content": "diff --git ...",
  "project_name": "octocat/hello-world",
  "target_branch": "main",
  "developer_name": "octocat"
}
```

# 8. Prompt 架构

建议把 Prompt 分成四层。

## 8.1 System Prompt

定义 AI 角色和边界：

```text
你是一个 AI PR Review 助手。
你只能根据用户提供的 PR 标题、描述、diff 和团队规则进行分析。
你不能假设不存在的仓库上下文。
你不能输出自动修改后的代码。
你不能建议自动合并 PR。
输出必须是合法 JSON。
```

## 8.2 Review Policy Prompt

定义问题类型、严重程度、风险等级规则。

```text
问题类型包括：逻辑问题、异常处理问题、安全问题、性能问题、可维护性问题、测试缺失、规范问题。
严重程度包括：高、中、低。
高风险问题必须有明确理由。
不确定的问题应降低置信度。
```

## 8.3 Team Rules Prompt

注入当前启用的团队规则：

```json
[
  {
    "id": "rule-1",
    "name": "修改核心逻辑必须补充测试",
    "type": "test",
    "severity": "medium",
    "description": "如果 PR 修改登录、支付、权限等核心逻辑，需要补充测试用例。"
  }
]
```

## 8.4 PR Context Prompt

注入 PR 标题、描述、diff 摘要和 diff 内容。

对于较大 diff，MVP 阶段可以限制最大输入长度：

```text
单次 Review 最大 diff 字符数：例如 30,000 ~ 80,000 字符
超出后提示用户拆分 PR 或只分析前 N 个文件
```

MVP 不做完整仓库知识库，所以不要承诺跨文件全局理解。

# 9. 安全架构

PRD 明确要求用户提交的代码内容应作为敏感信息处理，报告不能公开给无关人员，系统不能自动修改代码或自动合并 PR。

MVP 至少应实现：

```text
HTTPS
后端接口鉴权
数据库敏感字段加密或最小化存储
LLM API Key 只放服务端环境变量
禁止前端直接调用 LLM
日志中不打印完整 diff
报告访问必须校验创建人或项目成员
删除任务使用软删除
```

对于比赛 MVP，可以简化复杂权限，但仍建议保留基础用户身份：

```text
User
  └── owns ReviewTask
```

不要让所有人都能访问所有报告。

# 10. 部署架构

MVP 推荐 Docker Compose：

```text
nginx
  ├── frontend
  └── backend-api

backend-api
worker
postgres
redis
```

部署图：

```text
Internet
  │
  ▼
Nginx
  │
  ├── /               -> Frontend SPA
  └── /api            -> Backend API
                          │
                          ├── PostgreSQL
                          ├── Redis
                          └── AI Review Worker
                                  │
                                  ▼
                               LLM API
```

开发环境：

```text
docker compose up
```

生产 / 演示环境：

```text
一台云服务器即可
2C4G 可以跑 MVP
PostgreSQL + Redis + Backend + Worker + Frontend 同机部署
```

# 11. MVP 实现优先级

## 第一阶段：P0 主链路

先完成：

```text
新建 Review
提交 diff
异步生成报告
查看报告详情
问题列表展示
```

对应后端模块：

```text
ReviewTask
AIReviewWorker
Report
Issue
```

## 第二阶段：P1 规则与反馈

再完成：

```text
Review 规则配置
规则命中展示
历史记录筛选
单条问题反馈
```

## 第三阶段：展示增强

最后补充：

```text
首页统计卡片
风险统计
建议有用率
误报率
重新 Review
```

PRD 中也把创建 Review、输入 PR 变更、摘要生成、风险评估、问题识别、修改建议和报告详情列为 P0，把规则配置、历史记录、用户反馈和问题分类统计列为 P1，因此该实现顺序与产品优先级一致。

# 12. 最终推荐架构摘要

| 层级     | 技术 / 模块                                                |
| ------ | ------------------------------------------------------ |
| 前端     | React + TypeScript + Ant Design + Monaco Editor        |
| 后端 API | FastAPI + SQLAlchemy + Pydantic                        |
| 异步任务   | Celery / RQ                                            |
| 队列     | Redis                                                  |
| 数据库    | PostgreSQL                                             |
| AI 调用  | LLM Adapter                                            |
| 核心模块   | Review Task、Rule、Report、Issue、Feedback、AI Orchestrator |
| 部署     | Docker Compose + Nginx                                 |
| 架构风格   | 模块化单体，保留服务化扩展边界                                        |

一句话总结：

> 这个 MVP 最合适的架构不是复杂微服务，而是一个结构清晰的模块化单体系统：前端负责输入和报告展示，后端负责任务和数据管理，AI Worker 异步完成 diff 解析、规则匹配、LLM Review 和结构化报告生成。这样既能满足比赛展示，也能为后续接入 GitHub/GitLab、完整仓库知识库、IDE 插件和企业权限系统留下扩展空间。
