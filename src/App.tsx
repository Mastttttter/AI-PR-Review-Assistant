import { useEffect, useRef, useState } from 'react';
import { NavLink, Route, Routes, useNavigate, useParams } from 'react-router-dom';
import { ApiRequestError, apiClient } from './api';
import type { ApiClient, CreateReviewTaskRequest, DashboardResponse, FeedbackStatus, IssueSeverity, ReviewIssue, ReviewReport, ReviewRule, ReviewTask, ReviewTaskListQuery, ReviewTaskStatus, RiskLevel, RuleType, UpsertReviewRuleRequest } from './api';
import { confidenceLevelLabels, feedbackStatusLabels, issueSeverityLabels, issueTypeLabels, reviewTaskStatusLabels, riskLevelLabels, ruleTypeLabels } from './api';

const MAX_DIFF_LENGTH = 50_000;

const navigationItems = [
  { label: '工作台', path: '/' },
  { label: '新建 Review', path: '/reviews/new' },
  { label: '历史记录', path: '/history' },
  { label: '规则配置', path: '/rules' },

];

type ReviewTaskApi = Pick<ApiClient, 'createReviewTask'>;
type ReportClientApi = Pick<ApiClient, 'getReviewTask' | 'getReviewReport'>;
type HistoryClientApi = Pick<ApiClient, 'listReviewTasks'>;
type RulesClientApi = Pick<ApiClient, 'listReviewRules' | 'createReviewRule' | 'updateReviewRule' | 'enableReviewRule' | 'disableReviewRule' | 'deleteReviewRule'>;
type FeedbackClientApi = Pick<ApiClient, 'updateIssueFeedback'>;
type DashboardClientApi = Pick<ApiClient, 'getDashboardMetrics'>;

type FormErrors = Partial<Record<keyof CreateReviewTaskRequest | 'submit', string>>;

type AppProps = {
  client?: ReviewTaskApi & ReportClientApi & HistoryClientApi & RulesClientApi & FeedbackClientApi & DashboardClientApi;
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

function WorkbenchPage({ client }: { client: DashboardClientApi }) {
  const navigate = useNavigate();
  const [metrics, setMetrics] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    client.getDashboardMetrics()
      .then((data) => { if (active) { setMetrics(data); setLoading(false); } })
      .catch((e) => {
        if (active) {
          setError(e instanceof ApiRequestError ? e.message : '加载工作台数据失败，请稍后重试。');
          setLoading(false);
        }
      });
    return () => { active = false; };
  }, [client]);

  return (
    <PageCard title="首页 / 工作台" description="集中展示新建入口、最近任务、风险提醒和问题统计，为审查闭环提供清晰起点。">
      <div className="workbench-cta">
        <button type="button" className="primary-button" onClick={() => navigate('/reviews/new')}>新建 Review</button>
      </div>
      {loading ? <LoadingShell label="加载工作台数据..." /> : null}
      {error ? <ErrorShell message={error} /> : null}
      {metrics ? (
        <div className="metric-grid">
          <div><strong>{metrics.totalTasks}</strong><span>总任务</span></div>
          <div><strong>{metrics.totalIssues}</strong><span>总问题数</span></div>
          <div><strong>{metrics.tasksLast30Days}</strong><span>近 30 天任务</span></div>
          <div className="stat-high"><strong>{metrics.riskDistribution.high ?? 0}</strong><span>高风险任务</span></div>
          <div className="stat-medium"><strong>{metrics.riskDistribution.medium ?? 0}</strong><span>中风险任务</span></div>
          <div className="stat-low"><strong>{metrics.riskDistribution.low ?? 0}</strong><span>低风险任务</span></div>
        </div>
      ) : null}
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

  async function submitReview() {
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
      <div className="review-form">
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
          <button type="button" className="primary-button" disabled={isSubmitting} onClick={submitReview}>{isSubmitting ? '创建中' : '开始 Review'}</button>
        </div>
      </div>
    </PageCard>
  );
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function HistoryPage({ client }: { client: HistoryClientApi }) {
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<ReviewTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<ReviewTaskListQuery>({});

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    client.listReviewTasks(filters).then((data) => {
      if (active) { setTasks(data); setLoading(false); }
    }).catch((e) => {
      if (active) {
        setError(e instanceof ApiRequestError ? e.message : '加载历史记录失败，请稍后重试。');
        setLoading(false);
      }
    });

    return () => { active = false; };
  }, [filters, client]);

  function updateFilter<K extends keyof ReviewTaskListQuery>(key: K, value: ReviewTaskListQuery[K]) {
    setFilters((current) => ({ ...current, [key]: value || undefined }));
  }

  return (
    <PageCard title="历史记录" description="按任务状态、风险等级和项目维度查看历史 Review 记录。">
      <div className="history-page">
        <div className="filter-bar">
          <label className="filter-field">
            <span>项目</span>
            <input value={filters.projectName ?? ''} onChange={(e) => updateFilter('projectName', e.target.value || undefined)} placeholder="按项目筛选" />
          </label>
          <label className="filter-field">
            <span>风险等级</span>
            <select value={filters.riskLevel ?? ''} onChange={(e) => updateFilter('riskLevel', (e.target.value || undefined) as RiskLevel | undefined)}>
              <option value="">全部</option>
              <option value="high">高风险</option>
              <option value="medium">中风险</option>
              <option value="low">低风险</option>
            </select>
          </label>
          <label className="filter-field">
            <span>状态</span>
            <select value={filters.status ?? ''} onChange={(e) => updateFilter('status', (e.target.value || undefined) as ReviewTaskStatus | undefined)}>
              <option value="">全部</option>
              <option value="pending">待分析</option>
              <option value="running">分析中</option>
              <option value="completed">已完成</option>
              <option value="failed">分析失败</option>
            </select>
          </label>
          <label className="filter-field">
            <span>起始时间</span>
            <input type="date" value={filters.createdFrom ?? ''} onChange={(e) => updateFilter('createdFrom', e.target.value || undefined)} />
          </label>
          <label className="filter-field">
            <span>截止时间</span>
            <input type="date" value={filters.createdTo ?? ''} onChange={(e) => updateFilter('createdTo', e.target.value || undefined)} />
          </label>
        </div>

        {loading ? <LoadingShell label="加载历史记录..." /> : null}
        {error ? <ErrorShell message={error} /> : null}

        {!loading && !error && tasks.length === 0 ? (
          <p className="empty-state">暂无 Review 记录。</p>
        ) : null}

        {!loading && tasks.length > 0 ? (
          <div className="history-table-wrap">
            <table className="history-table">
              <thead>
                <tr>
                  <th>PR 标题</th>
                  <th>所属项目</th>
                  <th>创建人</th>
                  <th>创建时间</th>
                  <th>风险等级</th>
                  <th>问题数量</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((task) => (
                  <tr key={task.id} className="history-row" onClick={() => navigate(`/reviews/${task.id}`)}>
                    <td className="cell-title">{task.prTitle}</td>
                    <td>{task.projectName || '-'}</td>
                    <td>{task.createdBy || '-'}</td>
                    <td className="cell-time">{formatTime(task.createdAt)}</td>
                    <td>{task.riskLevel ? <span className={`risk-badge risk-${task.riskLevel}`}>{riskLevelLabels[task.riskLevel]}</span> : '-'}</td>
                    <td className="cell-num">{task.issueCount}</td>
                    <td><span className={`status-pill-task pill-${task.status}`}>{reviewTaskStatusLabels[task.status]}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </PageCard>
  );
}

type RuleFormErrors = Partial<Record<keyof UpsertReviewRuleRequest | 'submit', string>>;

const ruleTypeOptions: RuleType[] = ['test', 'style', 'security', 'documentation', 'naming', 'module'];
const severityOptions: IssueSeverity[] = ['low', 'medium', 'high'];

function emptyRuleForm(): UpsertReviewRuleRequest {
  return { name: '', description: '', type: 'style', severity: 'medium', enabled: true };
}

function validateRuleForm(form: UpsertReviewRuleRequest): RuleFormErrors {
  const errors: RuleFormErrors = {};
  if (!form.name.trim()) errors.name = '规则名称不能为空。';
  if (!form.description.trim()) errors.description = '规则描述不能为空。';
  return errors;
}

function RulesPage({ client }: { client: RulesClientApi }) {
  const [rules, setRules] = useState<ReviewRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<UpsertReviewRuleRequest>(emptyRuleForm());
  const [formErrors, setFormErrors] = useState<RuleFormErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  function loadRules() {
    setLoading(true);
    setError(null);
    client.listReviewRules()
      .then(setRules)
      .catch((e) => setError(e instanceof ApiRequestError ? e.message : '加载规则列表失败，请稍后重试。'))
      .finally(() => setLoading(false));
  }

  useEffect(() => { loadRules(); }, [client]);

  function openCreateForm() {
    setEditingId(null);
    setForm(emptyRuleForm());
    setFormErrors({});
    setActionError(null);
    setShowForm(true);
  }

  function openEditForm(rule: ReviewRule) {
    setEditingId(rule.id);
    setForm({ name: rule.name, description: rule.description, type: rule.type, severity: rule.severity, enabled: rule.enabled });
    setFormErrors({});
    setActionError(null);
    setShowForm(true);
  }

  function cancelForm() {
    setShowForm(false);
    setEditingId(null);
    setForm(emptyRuleForm());
    setFormErrors({});
  }

  async function submitForm() {
    const validationErrors = validateRuleForm(form);
    setFormErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) return;

    setSubmitting(true);
    setActionError(null);
    try {
      if (editingId) {
        await client.updateReviewRule(editingId, form);
      } else {
        await client.createReviewRule(form);
      }
      setShowForm(false);
      setEditingId(null);
      setForm(emptyRuleForm());
      loadRules();
    } catch (e) {
      setActionError(e instanceof ApiRequestError ? e.message : '保存规则失败，请稍后重试。');
    } finally {
      setSubmitting(false);
    }
  }

  async function toggleEnabled(rule: ReviewRule) {
    setActionError(null);
    try {
      const updated = rule.enabled
        ? await client.disableReviewRule(rule.id)
        : await client.enableReviewRule(rule.id);
      setRules((current) => current.map((r) => (r.id === rule.id ? updated : r)));
    } catch (e) {
      setActionError(e instanceof ApiRequestError ? e.message : '更新规则状态失败。');
    }
  }

  async function confirmDelete() {
    if (!confirmDeleteId) return;
    setActionError(null);
    try {
      await client.deleteReviewRule(confirmDeleteId);
      setRules((current) => current.filter((r) => r.id !== confirmDeleteId));
      setConfirmDeleteId(null);
    } catch (e) {
      setActionError(e instanceof ApiRequestError ? e.message : '删除规则失败。');
    }
  }

  function updateFormField<K extends keyof UpsertReviewRuleRequest>(key: K, value: UpsertReviewRuleRequest[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setFormErrors((current) => ({ ...current, [key]: undefined, submit: undefined }));
  }

  return (
    <PageCard title="规则配置" description="配置团队基础 Review 规则，统一测试、安全、规范和文档要求。">
      <div className="rules-page">
        <div className="rules-toolbar">
          <button type="button" className="primary-button" onClick={openCreateForm} disabled={showForm}>新建规则</button>
          {actionError ? <span className="rules-action-error">{actionError}</span> : null}
        </div>

        {showForm ? (
          <div className="rule-form-card">
            <h5 className="rule-form-title">{editingId ? '编辑规则' : '新建规则'}</h5>
            <div className="form-grid">
              <label className="form-field">
                <span>规则名称 *</span>
                <input value={form.name} onChange={(e) => updateFormField('name', e.target.value)} placeholder="例如：修改核心逻辑必须补充测试" aria-invalid={Boolean(formErrors.name)} />
                {formErrors.name ? <strong>{formErrors.name}</strong> : null}
              </label>
              <label className="form-field">
                <span>规则类型</span>
                <select value={form.type} onChange={(e) => updateFormField('type', e.target.value as RuleType)}>
                  {ruleTypeOptions.map((t) => <option key={t} value={t}>{ruleTypeLabels[t]}</option>)}
                </select>
              </label>
              <label className="form-field">
                <span>严重程度</span>
                <select value={form.severity} onChange={(e) => updateFormField('severity', e.target.value as IssueSeverity)}>
                  {severityOptions.map((s) => <option key={s} value={s}>{issueSeverityLabels[s]}</option>)}
                </select>
              </label>
              <div className="form-field form-checkbox">
                <span>启用状态</span>
                <label className="checkbox-row">
                  <input type="checkbox" checked={form.enabled} onChange={(e) => updateFormField('enabled', e.target.checked)} />
                  <span>{form.enabled ? '启用' : '停用'}</span>
                </label>
              </div>
            </div>
            <label className="form-field">
              <span>规则描述 *</span>
              <textarea value={form.description} onChange={(e) => updateFormField('description', e.target.value)} rows={3} placeholder="说明规则的具体内容和适用场景。" aria-invalid={Boolean(formErrors.description)} />
              {formErrors.description ? <strong>{formErrors.description}</strong> : null}
            </label>
            {formErrors.submit ? <strong className="form-submit-error">{formErrors.submit}</strong> : null}
            <div className="form-actions">
              <button type="button" className="secondary-button" onClick={cancelForm} disabled={submitting}>取消</button>
              <button type="button" className="primary-button" onClick={submitForm} disabled={submitting}>{submitting ? '保存中' : '保存'}</button>
            </div>
          </div>
        ) : null}

        {loading ? <LoadingShell label="加载规则列表..." /> : null}
        {error ? <ErrorShell message={error} /> : null}

        {!loading && !error && rules.length === 0 ? (
          <p className="empty-state">暂无规则。点击"新建规则"添加团队 Review 规则。</p>
        ) : null}

        {!loading && rules.length > 0 ? (
          <div className="rules-table-wrap">
            <table className="rules-table">
              <thead>
                <tr>
                  <th>规则名称</th>
                  <th>规则类型</th>
                  <th>严重程度</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((rule) => (
                  <tr key={rule.id} className="rule-row">
                    <td>
                      <div className="rule-name-cell">
                        <strong>{rule.name}</strong>
                        <small>{rule.description}</small>
                      </div>
                    </td>
                    <td><span className="rule-type-badge">{ruleTypeLabels[rule.type]}</span></td>
                    <td><span className={`severity-badge severity-${rule.severity}`}>{issueSeverityLabels[rule.severity]}</span></td>
                    <td>
                      <button type="button" className={`rule-toggle toggle-${rule.enabled ? 'on' : 'off'}`} onClick={() => toggleEnabled(rule)}>
                        {rule.enabled ? '启用中' : '已停用'}
                      </button>
                    </td>
                    <td>
                      <div className="rule-actions">
                        <button type="button" className="icon-button" onClick={() => openEditForm(rule)} disabled={showForm}>编辑</button>
                        {confirmDeleteId === rule.id ? (
                          <>
                            <button type="button" className="icon-button danger" onClick={confirmDelete}>确认删除</button>
                            <button type="button" className="icon-button" onClick={() => setConfirmDeleteId(null)}>取消</button>
                          </>
                        ) : (
                          <button type="button" className="icon-button danger" onClick={() => setConfirmDeleteId(rule.id)} disabled={showForm}>删除</button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </PageCard>
  );
}

function ReportPage({ client, pollIntervalMs = 2_000 }: { client: ReportClientApi & FeedbackClientApi; pollIntervalMs?: number }) {
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
    return <ReportDetailCard report={report} client={client} />;
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

type FeedbackOption = Exclude<FeedbackStatus, 'none'>;
const feedbackOptions: { value: FeedbackOption; label: string }[] = [
  { value: 'useful', label: '有用' },
  { value: 'useless', label: '无用' },
  { value: 'false_positive', label: '误报' },
  { value: 'adopted', label: '已采纳' },
  { value: 'ignored', label: '暂不处理' },
];

function FeedbackControls({
  issueId,
  currentStatus,
  client,
  onStatusChange,
}: {
  issueId: string;
  currentStatus: FeedbackStatus;
  client: FeedbackClientApi;
  onStatusChange: (issueId: string, status: FeedbackStatus) => void;
}) {
  const [submittingOption, setSubmittingOption] = useState<FeedbackOption | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submitFeedback(option: FeedbackOption) {
    setSubmittingOption(option);
    setError(null);
    try {
      const response = await client.updateIssueFeedback(issueId, { feedbackStatus: option });
      onStatusChange(issueId, response.feedbackStatus);
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : '提交反馈失败');
    } finally {
      setSubmittingOption(null);
    }
  }

  return (
    <div className="feedback-controls">
      <span className="feedback-controls-label">反馈:</span>
      <div className="feedback-options">
        {feedbackOptions.map((option) => (
          <button
            key={option.value}
            type="button"
            className={`feedback-option${currentStatus === option.value ? ' active' : ''}`}
            disabled={submittingOption !== null}
            onClick={() => submitFeedback(option.value)}
          >
            {submittingOption === option.value ? '提交中...' : option.label}
          </button>
        ))}
      </div>
      {error ? <span className="feedback-error">{error}</span> : null}
    </div>
  );
}

function ReportDetailCard({ report, client }: { report: ReviewReport; client: FeedbackClientApi }) {
  const [issueStatuses, setIssueStatuses] = useState<Record<string, FeedbackStatus>>(() => {
    const initial: Record<string, FeedbackStatus> = {};
    for (const issue of report.issues) {
      initial[issue.id] = issue.feedbackStatus;
    }
    return initial;
  });

  function handleStatusChange(issueId: string, status: FeedbackStatus) {
    setIssueStatuses((prev) => ({ ...prev, [issueId]: status }));
  }

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
                        <FeedbackBadge status={issueStatuses[issue.id] ?? issue.feedbackStatus} />
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
                      <FeedbackControls
                        issueId={issue.id}
                        currentStatus={issueStatuses[issue.id] ?? issue.feedbackStatus}
                        client={client}
                        onStatusChange={handleStatusChange}
                      />
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
        <Route path="/" element={<WorkbenchPage client={client} />} />
        <Route path="/reviews/new" element={<NewReviewPage client={client} />} />
        <Route path="/history" element={<HistoryPage client={client} />} />
        <Route path="/rules" element={<RulesPage client={client} />} />
        <Route path="/reviews/:taskId" element={<ReportPage client={client} pollIntervalMs={pollIntervalMs} />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Shell>
  );
}
