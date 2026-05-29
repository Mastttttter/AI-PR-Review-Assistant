import { NavLink, Route, Routes, useParams } from 'react-router-dom';

const navigationItems = [
  { label: '工作台', path: '/' },
  { label: '新建 Review', path: '/reviews/new' },
  { label: '历史记录', path: '/history' },
  { label: '规则配置', path: '/rules' },
  { label: '报告详情', path: '/reviews/demo-report' }
];

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

function NewReviewPage() {
  return <PageCard title="新建 Review" description="提交 PR 标题、描述与代码 diff 后进入 Review 生成状态。" />;
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

export function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<WorkbenchPage />} />
        <Route path="/reviews/new" element={<NewReviewPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/rules" element={<RulesPage />} />
        <Route path="/reviews/:taskId" element={<ReportPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Shell>
  );
}
