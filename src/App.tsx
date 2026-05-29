import { FormEvent, useEffect, useRef, useState } from 'react';
import { NavLink, Route, Routes, useNavigate, useParams } from 'react-router-dom';
import { ApiRequestError, apiClient } from './api';
import type { ApiClient, CreateReviewTaskRequest, IssueSeverity, ReviewReport, ReviewTask, ReviewTaskStatus } from './api';
import { confidenceLevelLabels, issueSeverityLabels, issueTypeLabels, reviewTaskStatusLabels, riskLevelLabels } from './api';

const MAX_DIFF_LENGTH = 50_000;

const navigationItems = [
  { label: '工作台', path: '/' },
  { label: '新建 Review', path: '/reviews/new' },
  { label: '历史记录', path: '/history' },
  { label: '规则配置', path: '/rules' },
  { label: '报告详情', path: '/reviews/demo-report' }
];

type ReviewTaskApi = Pick<ApiClient, 'createReviewTask'>;
type ReportClientApi = Pick<ApiClient, 'getReviewTask' | 'getReviewReport'>;

type FormErrors = Partial<Record<keyof CreateReviewTaskRequest | 'submit', string>>;

type AppProps = {
  client?: ReviewTaskApi & ReportClientApi;
  pollIntervalMs?: number;
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

function ReportPage({ client, pollIntervalMs = 2_000 }: { client: ReportClientApi; pollIntervalMs?: number }) {
  const { taskId } = useParams();
  const [task, setTask] = useState<ReviewTask | null>(null);
  const [report, setReport] = useState<ReviewReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const statusRef = useRef<ReviewTaskStatus | null>(null);

  useEffect(() => {
    if (!taskId) return;

    let active = true;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function poll() {
      if (!active) return;
      try {
        const taskData = await client.getReviewTask(taskId!);
        if (!active) return;

        statusRef.current = taskData.status;
        setTask(taskData);

        if (taskData.status === 'completed') {
          try {
            const reportData = await client.getReviewReport(taskId!);
            if (active) setReport(reportData);
          } catch (e) {
            if (active) setError(e instanceof ApiRequestError ? e.message : '获取报告失败，请稍后重试。');
          }
        } else if (taskData.status === 'failed') {
          setError('Review 分析失败。任务上下文已保留，可返回重新提交。');
        } else {
          timer = setTimeout(poll, pollIntervalMs);
        }
      } catch (e) {
        if (active) {
          const message = e instanceof ApiRequestError ? e.message : '无法获取任务状态，请稍后重试。';
          setError(message);
        }
      }
    }

    poll();

    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [taskId, client]);

  if (report) {
    return <ReportDetailCard report={report} />;
  }

  if (error) {
    return (
      <PageCard title="Review 报告详情" description={`任务 ${taskId ?? '-'} 的审查状态与结果。`}>
        <ErrorShell message={error} />
        {task ? <TaskContextBar task={task} /> : null}
      </PageCard>
    );
  }

  const label = task ? reviewTaskStatusLabels[task.status] : '加载中';

  return (
    <PageCard title="Review 报告详情" description={`任务 ${taskId ?? '-'} 的审查状态与结果。`}>
      <LoadingShell label={`${label}...`} />
      {task ? <TaskContextBar task={task} /> : null}
    </PageCard>
  );
}

function TaskContextBar({ task }: { task: ReviewTask }) {
  return (
    <div className="task-context-bar">
      <span>PR: {task.prTitle}</span>
      {task.projectName ? <span>项目: {task.projectName}</span> : null}
      {task.developerName ? <span>开发者: {task.developerName}</span> : null}
      <span className={`status-pill-task pill-${task.status}`}>{reviewTaskStatusLabels[task.status]}</span>
    </div>
  );
}

function SeverityBadge({ severity }: { severity: IssueSeverity }) {
  return <span className={`issue-severity-badge badge-${severity}`}>{issueSeverityLabels[severity]}</span>;
}

function FeedbackBadge({ status }: { status: string }) {
  if (!status || status === 'none') return null;
  const labels: Record<string, string> = {
    useful: '有用', useless: '无用', false_positive: '误报', adopted: '已采纳', ignored: '暂不处理'
  };
  return <span className="feedback-badge">{labels[status] ?? status}</span>;
}

function ReportDetailCard({ report }: { report: ReviewReport }) {
  const orderMap = { high: 0, medium: 1, low: 2 };
  const sorted = [...report.issues].sort(
    (a, b) => (orderMap[a.severity] ?? 2) - (orderMap[b.severity] ?? 2)
  );

  const groups = new Map<string, typeof report.issues>();
  const severityOrder: IssueSeverity[] = ['high', 'medium', 'low'];
  for (const sev of severityOrder) {
    const items = sorted.filter((i) => i.severity === sev);
    if (items.length > 0) groups.set(sev, items);
  }

  const task = report.task;

  return (
    <PageCard title="Review 报告详情" description={`任务 ${task.id} 的审查结果。`}>
      <div className="report-detail">
        <section className="report-section">
          <h4 className="report-section-title">PR 基本信息</h4>
          <dl className="pr-meta-list">
            <div><dt>PR 标题</dt><dd>{task.prTitle}</dd></div>
            {task.prDescription ? <div><dt>PR 描述</dt><dd>{task.prDescription}</dd></div> : null}
            {task.projectName ? <div><dt>所属项目</dt><dd>{task.projectName}</dd></div> : null}
            {task.targetBranch ? <div><dt>目标分支</dt><dd>{task.targetBranch}</dd></div> : null}
            {task.developerName ? <div><dt>开发者</dt><dd>{task.developerName}</dd></div> : null}
            <div><dt>创建时间</dt><dd>{new Date(task.createdAt).toLocaleString('zh-CN')}</dd></div>
            <div><dt>Review 状态</dt><dd><span className={`status-pill-task pill-${task.status}`}>{reviewTaskStatusLabels[task.status]}</span></dd></div>
          </dl>
        </section>

        <section className="report-section">
          <h4 className="report-section-title">AI 摘要</h4>
          <p className="summary-purpose">{report.summary.purpose}</p>
          {report.summary.businessImpact ? <p className="report-meta">业务影响: {report.summary.businessImpact}</p> : null}
          {report.summary.changedModules.length > 0 ? <p className="report-meta">涉及模块: {report.summary.changedModules.join(', ')}</p> : null}
          {report.summary.keyFiles.length > 0 ? <p className="report-meta">关键文件: {report.summary.keyFiles.join(', ')}</p> : null}
          {report.summary.testOrSecurityNotes ? <p className="report-meta">安全/测试: {report.summary.testOrSecurityNotes}</p> : null}
        </section>

        <section className="report-section">
          <h4 className="report-section-title">
            风险等级
            <span className={`risk-badge risk-${report.risk.level}`}>{riskLevelLabels[report.risk.level]}</span>
          </h4>
          <ul className="reason-list">
            {report.risk.reasons.map((reason, i) => <li key={i}>{reason}</li>)}
          </ul>
        </section>

        <section className="report-section">
          <h4 className="report-section-title">问题统计</h4>
          <div className="issue-stat-grid">
            <div><strong>{report.issueStats.total}</strong><span>总计</span></div>
            <div className="stat-high"><strong>{report.issueStats.high}</strong><span>高风险</span></div>
            <div className="stat-medium"><strong>{report.issueStats.medium}</strong><span>中风险</span></div>
            <div className="stat-low"><strong>{report.issueStats.low}</strong><span>低风险</span></div>
            <div className="stat-rule"><strong>{report.issueStats.ruleHits}</strong><span>命中规则</span></div>
          </div>
        </section>

        <section className="report-section">
          <h4 className="report-section-title">问题列表</h4>
          {sorted.length === 0 ? <p className="report-meta">未发现问题。</p> : null}
          {severityOrder.map((sev) => {
            const items = groups.get(sev);
            if (!items) return null;
            return (
              <div key={sev} className="issue-group">
                <h5 className={`issue-group-header group-${sev}`}>
                  <SeverityBadge severity={sev} />
                  <span>{severityGroupLabel[sev]} ({items.length})</span>
                </h5>
                <ol className="issue-list">
                  {items.map((issue) => (
                    <li key={issue.id} className={`issue-card severity-${issue.severity}`}>
                      <div className="issue-header">
                        <SeverityBadge severity={issue.severity} />
                        <span className="issue-type-badge">{issueTypeLabels[issue.type]}</span>
                        <span className={`confidence-badge conf-${issue.confidence}`}>{confidenceLevelLabels[issue.confidence]}</span>
                        <FeedbackBadge status={issue.feedbackStatus} />
                        <strong className="issue-title">{issue.title}</strong>
                      </div>
                      <p className="issue-description">{issue.description}</p>
                      {issue.location.filePath || issue.location.codeSnippet ? (
                        <div className="issue-location-block">
                          {issue.location.filePath ? (
                            <span className="issue-location">位置: {issue.location.filePath}{issue.location.lineHint ? ` (${issue.location.lineHint})` : ''}</span>
                          ) : null}
                          {issue.location.codeSnippet ? <pre className="issue-code-snippet"><code>{issue.location.codeSnippet}</code></pre> : null}
                        </div>
                      ) : null}
                      <p className="issue-suggestion">{issue.suggestion}</p>
                      {issue.matchedRuleIds.length > 0 ? (
                        <p className="issue-rules">命中规则: {issue.matchedRuleIds.join(', ')}</p>
                      ) : null}
                    </li>
                  ))}
                </ol>
              </div>
            );
          })}
        </section>
      </div>
    </PageCard>
  );
}

const severityGroupLabel: Record<IssueSeverity, string> = {
  high: '高风险问题',
  medium: '中风险问题',
  low: '低风险问题',
};

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

export function App({ client = apiClient, pollIntervalMs }: AppProps) {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<WorkbenchPage />} />
        <Route path="/reviews/new" element={<NewReviewPage client={client} />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/rules" element={<RulesPage />} />
        <Route path="/reviews/:taskId" element={<ReportPage client={client} pollIntervalMs={pollIntervalMs} />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Shell>
  );
}
