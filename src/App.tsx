import { FormEvent, useState } from 'react';
import { NavLink, Route, Routes, useNavigate, useParams } from 'react-router-dom';
import { ApiRequestError, apiClient } from './api';
import type { ApiClient, CreateReviewTaskRequest } from './api';

const MAX_DIFF_LENGTH = 50_000;

const navigationItems = [
  { label: '工作台', path: '/' },
  { label: '新建 Review', path: '/reviews/new' },
  { label: '历史记录', path: '/history' },
  { label: '规则配置', path: '/rules' },
  { label: '报告详情', path: '/reviews/demo-report' }
];

type ReviewTaskApi = Pick<ApiClient, 'createReviewTask'>;

type FormErrors = Partial<Record<keyof CreateReviewTaskRequest | 'submit', string>>;

type AppProps = {
  client?: ReviewTaskApi;
};

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="主导航">
        <div className="brand-block">
          <span className="brand-mark">PR</span>
          <div>
            <p className="eyebrow">AI Review Control</p>
            <h1>代码审查助手</h1>
          </div>
        </div>
        <nav className="nav-list">
          {navigationItems.map((item) => (
            <NavLink key={item.path} to={item.path} end={item.path === '/'} className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="security-note">
          <span>敏感数据模式</span>
          <strong>Diff 与报告不在浏览器控制台输出</strong>
        </div>
      </aside>
      <main className="main-panel">
        <header className="topbar">
          <div>
            <p className="eyebrow">MVP v1.0</p>
            <h2>Pull Request 审查工作台</h2>
          </div>
          <span className="status-pill">演示环境</span>
        </header>
        {children}
      </main>
    </div>
  );
}

function PageCard({ title, description, children }: { title: string; description: string; children?: React.ReactNode }) {
  return (
    <section className="page-card">
      <p className="eyebrow">AI PR Review Assistant</p>
      <h3>{title}</h3>
      <p className="page-description">{description}</p>
      {children}
    </section>
  );
}

function WorkbenchPage() {
  return (
    <PageCard title="首页 / 工作台" description="集中展示新建入口、最近任务、风险提醒和问题统计，为审查闭环提供清晰起点。">
      <div className="metric-grid">
        <div><strong>3</strong><span>待关注 Review</span></div>
        <div><strong>1</strong><span>高风险任务</span></div>
        <div><strong>12</strong><span>本周问题</span></div>
      </div>
    </PageCard>
  );
}

function validateReviewRequest(request: CreateReviewTaskRequest): FormErrors {
  const errors: FormErrors = {};
  if (!request.prTitle.trim()) {
    errors.prTitle = 'PR 标题不能为空。';
  }
  if (!request.diffContent.trim()) {
    errors.diffContent = '代码变更内容不能为空。';
  } else if (request.diffContent.length > MAX_DIFF_LENGTH) {
    errors.diffContent = '代码变更内容不能超过 50,000 个字符。';
  }
  return errors;
}

function emptyToUndefined(value: string): string | undefined {
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

function NewReviewPage({ client }: { client: ReviewTaskApi }) {
  const navigate = useNavigate();
  const [form, setForm] = useState<CreateReviewTaskRequest>({
    prTitle: '',
    prDescription: '',
    projectName: '',
    targetBranch: '',
    developerName: '',
    diffContent: ''
  });
  const [errors, setErrors] = useState<FormErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const diffCount = form.diffContent.length;
  const diffIsOverLimit = diffCount > MAX_DIFF_LENGTH;

  function updateField(field: keyof CreateReviewTaskRequest, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined, submit: undefined }));
  }

  async function submitReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const request: CreateReviewTaskRequest = {
      prTitle: form.prTitle.trim(),
      prDescription: emptyToUndefined(form.prDescription ?? ''),
      projectName: emptyToUndefined(form.projectName ?? ''),
      targetBranch: emptyToUndefined(form.targetBranch ?? ''),
      developerName: emptyToUndefined(form.developerName ?? ''),
      diffContent: form.diffContent
    };
    const validationErrors = validateReviewRequest(request);
    setErrors(validationErrors);

    if (Object.keys(validationErrors).length > 0) {
      return;
    }

    setIsSubmitting(true);
    try {
      const result = await client.createReviewTask(request);
      navigate(`/reviews/${result.taskId}`, { state: { reviewStatus: result.status } });
    } catch (error) {
      const message = error instanceof ApiRequestError ? error.message : '创建 Review 任务失败，请稍后重试。';
      setErrors({ submit: message });
      setIsSubmitting(false);
    }
  }

  return (
    <PageCard title="新建 Review" description="提交 PR 标题、描述与代码 diff 后进入 Review 生成状态。">
      <form className="review-form" onSubmit={submitReview} noValidate>
        {isSubmitting ? <LoadingShell label="正在创建 Review 任务" /> : null}
        {errors.submit ? <ErrorShell message={errors.submit} /> : null}

        <div className="form-grid">
          <label className="form-field">
            <span>PR 标题 *</span>
            <input value={form.prTitle} onChange={(event) => updateField('prTitle', event.target.value)} placeholder="例如：优化用户登录逻辑" aria-invalid={Boolean(errors.prTitle)} />
            {errors.prTitle ? <strong>{errors.prTitle}</strong> : null}
          </label>

          <label className="form-field">
            <span>所属项目</span>
            <input value={form.projectName} onChange={(event) => updateField('projectName', event.target.value)} placeholder="例如：user-center" />
          </label>

          <label className="form-field">
            <span>目标分支</span>
            <input value={form.targetBranch} onChange={(event) => updateField('targetBranch', event.target.value)} placeholder="例如：main" />
          </label>

          <label className="form-field">
            <span>开发者名称</span>
            <input value={form.developerName} onChange={(event) => updateField('developerName', event.target.value)} placeholder="例如：Alice" />
          </label>
        </div>

        <label className="form-field">
          <span>PR 描述</span>
          <textarea value={form.prDescription} onChange={(event) => updateField('prDescription', event.target.value)} rows={4} placeholder="说明改动背景、影响范围和需要重点关注的风险。" />
        </label>

        <label className="form-field diff-field">
          <span>代码变更内容 *</span>
          <textarea value={form.diffContent} onChange={(event) => updateField('diffContent', event.target.value)} rows={12} placeholder="粘贴 git diff 或关键代码片段。" aria-invalid={Boolean(errors.diffContent || diffIsOverLimit)} />
          <small className={diffIsOverLimit ? 'limit-count over-limit' : 'limit-count'}>{diffCount.toLocaleString()} / 50,000</small>
          {errors.diffContent ? <strong>{errors.diffContent}</strong> : null}
        </label>

        <div className="form-actions">
          <button type="button" className="secondary-button" onClick={() => navigate('/')} disabled={isSubmitting}>取消</button>
          <button type="submit" className="primary-button" disabled={isSubmitting}>{isSubmitting ? '创建中' : '开始 Review'}</button>
        </div>
      </form>
    </PageCard>
  );
}

function HistoryPage() {
  return <PageCard title="历史记录" description="按任务状态、风险等级和项目维度查看历史 Review 记录。" />;
}

function RulesPage() {
  return <PageCard title="规则配置" description="配置团队基础 Review 规则，统一测试、安全、规范和文档要求。" />;
}

function ReportPage() {
  const { taskId } = useParams();
  return (
    <PageCard title="Review 报告详情" description={`展示任务 ${taskId ?? '未知'} 的摘要、风险等级、问题列表、规则命中和反馈状态。`}>
      <LoadingShell label="报告生成中" />
      <ErrorShell message="如果报告生成失败，页面会保留任务上下文并展示可恢复提示。" />
    </PageCard>
  );
}

function NotFoundPage() {
  return <PageCard title="页面不存在" description="当前路径没有对应页面，请通过左侧导航返回 MVP 功能入口。" />;
}

export function LoadingShell({ label = '加载中' }: { label?: string }) {
  return (
    <div className="state-shell" role="status" aria-live="polite">
      <span className="loader" />
      <span>{label}</span>
    </div>
  );
}

export function ErrorShell({ message }: { message: string }) {
  return (
    <div className="state-shell error" role="alert">
      <span>!</span>
      <span>{message}</span>
    </div>
  );
}

export function App({ client = apiClient }: AppProps) {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<WorkbenchPage />} />
        <Route path="/reviews/new" element={<NewReviewPage client={client} />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/rules" element={<RulesPage />} />
        <Route path="/reviews/:taskId" element={<ReportPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Shell>
  );
}
