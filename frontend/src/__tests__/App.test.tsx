import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { App } from '../App';
import { ApiRequestError } from '../api';
import type { DashboardResponse, FetchPrResponse, ReviewReport, ReviewTask, ReviewTaskListQuery, SettingsResponse } from '../api';
import { emptyReport, minimalReport, mockReviewReport, mockReviewTask, mockTaskList } from '../test-fixtures/mockReview';

async function neverCalled(): Promise<never> {
  throw new Error('should not be called');
}

function neverReport(_id: string): Promise<ReviewReport> {
  throw new Error('should not be called');
}

async function neverTasks(_query?: ReviewTaskListQuery): Promise<ReviewTask[]> {
  throw new Error('should not be called');
}

async function emptyRules(): Promise<[]> {
  return [];
}

function neverRuleMutation(..._args: unknown[]): Promise<never> {
  throw new Error('should not be called');
}

function neverFeedback(..._args: unknown[]): Promise<never> {
  throw new Error('should not be called');
}

async function neverSettings(): Promise<never> {
  throw new Error('should not be called');
}

async function emptyDashboard(): Promise<DashboardResponse> {
  return {
    totalTasks: 0,
    tasksLast30Days: 0,
    totalIssues: 0,
    riskDistribution: { high: 0, medium: 0, low: 0 },
    usefulRate: 0,
    falsePositiveRate: 0,
    adoptionRate: 0,
  };
}

function renderAt(path: string, client: Record<string, unknown> = { createReviewTask: neverCalled, fetchPrInfo: neverCalled, getReviewTask: neverCalled, getReviewReport: neverCalled, listReviewTasks: neverTasks, listReviewRules: emptyRules, createReviewRule: neverRuleMutation, updateReviewRule: neverRuleMutation, enableReviewRule: neverRuleMutation, disableReviewRule: neverRuleMutation, deleteReviewRule: neverRuleMutation, updateIssueFeedback: neverFeedback, getDashboardMetrics: emptyDashboard, getSettings: neverSettings, updateSettings: neverSettings, testSettingsConnection: neverSettings }, pollIntervalMs?: number) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App client={client as never} pollIntervalMs={pollIntervalMs} />
    </MemoryRouter>
  );
}

describe('application shell routes', () => {
  it.each([
    ['/', '首页 / 工作台'],
    ['/reviews/new', '新建 Review'],
    ['/history', '历史记录'],
    ['/rules', '规则配置'],
    ['/settings', '助手设置'],
  ])('renders %s route', (path, heading) => {
    renderAt(path);
    expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument();
  });

  it('shows a safe fallback for unknown routes', () => {
    renderAt('/missing/page');
    expect(screen.getByRole('heading', { name: '页面不存在' })).toBeInTheDocument();
  });

  it('navigates between MVP pages without dead links', async () => {
    const user = userEvent.setup();
    renderAt('/');

    await user.click(screen.getByRole('link', { name: '新建 Review' }));
    expect(screen.getByRole('heading', { name: '新建 Review' })).toBeInTheDocument();

    await user.click(screen.getByRole('link', { name: '历史记录' }));
    expect(screen.getByRole('heading', { name: '历史记录' })).toBeInTheDocument();

    await user.click(screen.getByRole('link', { name: '规则配置' }));
    expect(screen.getByRole('heading', { name: '规则配置' })).toBeInTheDocument();

    await user.click(screen.getByRole('link', { name: '助手设置' }));
    expect(screen.getByRole('heading', { name: '助手设置' })).toBeInTheDocument();
  });
});

describe('Review status polling flow', () => {
  it('polls task status and auto-reveals the report when completed', async () => {
    let pollCount = 0;
    const getReviewTask = vi.fn(async (_id: string): Promise<ReviewTask> => {
      pollCount++;
      if (pollCount < 3) {
        return { ...mockReviewTask, id: 'task-abc', status: 'running' };
      }
      return { ...mockReviewTask, id: 'task-abc', status: 'completed' };
    });
    const getReviewReport = vi.fn(async (_id: string): Promise<ReviewReport> => mockReviewReport);

    renderAt('/reviews/task-abc', {
      createReviewTask: neverCalled,
      getReviewTask,
      getReviewReport,
      updateIssueFeedback: neverFeedback,
    } as never, 0);

    // Initial render shows loading, then first poll resolves to running
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('分析中...'));
    expect(getReviewTask).toHaveBeenCalledWith('task-abc');

    // After all polls complete (interval=0), report appears
    await waitFor(() => expect(screen.getByText('AI 摘要')).toBeInTheDocument());
    expect(getReviewReport).toHaveBeenCalledWith('task-abc');
    expect(pollCount).toBeGreaterThanOrEqual(3);
  });

  it('shows failed state preserving task context', async () => {
    const failedTask: ReviewTask = {
      ...mockReviewTask,
      id: 'task-fail',
      prTitle: '失败的任务',
      status: 'failed',
    };

    const getReviewTask = vi.fn(async () => failedTask);
    const getReviewReport = vi.fn(async () => { throw new Error('should not be called'); });

    renderAt('/reviews/task-fail', {
      createReviewTask: neverCalled,
      getReviewTask,
      getReviewReport,
    } as never, 0);

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Review 分析失败'));
    expect(screen.getByText('PR: 失败的任务')).toBeInTheDocument();
    expect(getReviewReport).not.toHaveBeenCalled();
  });

  it('handles network errors during polling', async () => {
    const getReviewTask = vi.fn(async () => { throw new Error('Network error'); });

    renderAt('/reviews/task-err', {
      createReviewTask: neverCalled,
      getReviewTask,
      getReviewReport: neverReport,
    } as never, 0);

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('无法获取任务状态'));
  });

  it('handles pending state on first poll', async () => {
    const getReviewTask = vi.fn(async () => ({ ...mockReviewTask, id: 'task-pending', status: 'pending' as const }));

    renderAt('/reviews/task-pending', {
      createReviewTask: neverCalled,
      getReviewTask,
      getReviewReport: neverReport,
    } as never, 0);

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('待分析...'));
  });
});

function completedClient(report: ReviewReport) {
  const getReviewTask = vi.fn(async () => ({ ...report.task, status: 'completed' as const }));
  const getReviewReport = vi.fn(async () => report);
  return { createReviewTask: neverCalled, getReviewTask, getReviewReport, updateIssueFeedback: neverFeedback };
}

describe('Review report detail page', () => {
  it('renders PR info section with all metadata', async () => {
    renderAt('/reviews/task-001', completedClient(mockReviewReport) as never, 0);

    await waitFor(() => expect(screen.getByText('PR 基本信息')).toBeInTheDocument());
    expect(screen.getByText('优化用户登录逻辑')).toBeInTheDocument();
    expect(screen.getByText('新增 token 刷新机制')).toBeInTheDocument();
    expect(screen.getByText('user-center')).toBeInTheDocument();
    expect(screen.getByText('main')).toBeInTheDocument();
    expect(screen.getByText('Alice')).toBeInTheDocument();
  });

  it('renders AI summary with all fields', async () => {
    renderAt('/reviews/task-001', completedClient(mockReviewReport) as never, 0);

    await waitFor(() => expect(screen.getByText('AI 摘要')).toBeInTheDocument());
    expect(screen.getByText('新增登录 token 刷新流程。')).toBeInTheDocument();
    expect(screen.getByText(/业务影响/)).toBeInTheDocument();
    expect(screen.getByText(/认证模块/)).toBeInTheDocument();
    expect(screen.getByText('关键文件: src/auth/AuthService.ts')).toBeInTheDocument();
    expect(screen.getByText('安全/测试: 涉及认证逻辑，缺少异常场景测试。')).toBeInTheDocument();
  });

  it('renders risk level with reasons', async () => {
    renderAt('/reviews/task-001', completedClient(mockReviewReport) as never, 0);

    await waitFor(() => expect(screen.getByText('风险等级')).toBeInTheDocument());
    const riskSection = screen.getByText('风险等级').closest('.report-section')!;
    expect(riskSection.querySelector('.risk-badge.risk-high')).toHaveTextContent('高风险');
    expect(screen.getByText('修改认证核心流程')).toBeInTheDocument();
    expect(screen.getByText('未发现对应测试')).toBeInTheDocument();
  });

  it('shows issue stats including rule hits', async () => {
    renderAt('/reviews/task-001', completedClient(mockReviewReport) as never, 0);

    await waitFor(() => expect(screen.getByText('问题统计')).toBeInTheDocument());
    expect(screen.getByText('总计')).toBeInTheDocument();
    expect(screen.getByText('命中规则')).toBeInTheDocument();
  });

  it('groups and sorts issues by severity with section headers', async () => {
    renderAt('/reviews/task-001', completedClient(mockReviewReport) as never, 0);

    await waitFor(() => expect(screen.getByText('问题列表')).toBeInTheDocument());
    expect(screen.getByText(/高风险问题/)).toBeInTheDocument();
    expect(screen.getByText(/中风险问题/)).toBeInTheDocument();

    const highSection = screen.getByText(/高风险问题/).closest('.issue-group');
    const mediumSection = screen.getByText(/中风险问题/).closest('.issue-group');

    expect(highSection!.compareDocumentPosition(mediumSection!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('shows confidence badges and feedback state on issues', async () => {
    renderAt('/reviews/task-001', completedClient(mockReviewReport) as never, 0);

    await waitFor(() => expect(screen.getByText('问题列表')).toBeInTheDocument());
    expect(screen.getByText('高置信度')).toBeInTheDocument();
    expect(screen.getByText('中置信度')).toBeInTheDocument();
    const feedbackBadge = document.querySelector('.feedback-badge');
    expect(feedbackBadge).toHaveTextContent('有用');
  });

  it('renders code location with snippet', async () => {
    renderAt('/reviews/task-001', completedClient(mockReviewReport) as never, 0);

    await waitFor(() => expect(screen.getByText('问题列表')).toBeInTheDocument());
    expect(screen.getByText(/位置: src\/auth\/AuthService.ts.*L42-L58/)).toBeInTheDocument();
    expect(screen.getByText('refreshToken();')).toBeInTheDocument();
  });

  it('shows matched rule IDs on issues', async () => {
    renderAt('/reviews/task-001', completedClient(mockReviewReport) as never, 0);

    await waitFor(() => expect(screen.getByText('问题列表')).toBeInTheDocument());
    expect(screen.getByText(/命中规则.*rule-001/)).toBeInTheDocument();
  });

  it('handles empty issue list gracefully', async () => {
    renderAt('/reviews/task-empty', completedClient(emptyReport) as never, 0);

    await waitFor(() => expect(screen.getByText('问题列表')).toBeInTheDocument());
    expect(screen.getByText('未发现问题。')).toBeInTheDocument();
    const riskSection = screen.getByText('风险等级').closest('.report-section')!;
    expect(riskSection.querySelector('.risk-badge.risk-low')).toHaveTextContent('低风险');
    expect(screen.queryByText(/高风险问题/)).not.toBeInTheDocument();
  });

  it('handles minimal report without crashing', async () => {
    renderAt('/reviews/task-min', completedClient(minimalReport) as never, 0);

    await waitFor(() => expect(screen.getByText('问题列表')).toBeInTheDocument());
    expect(screen.getByText('空值检查')).toBeInTheDocument();
    expect(screen.getByText('添加空值检查。')).toBeInTheDocument();
    expect(screen.getByText('低置信度')).toBeInTheDocument();
    expect(screen.queryByText(/业务影响/)).not.toBeInTheDocument();
  });

  it('displays PR link when prUrl is present', async () => {
    const reportWithUrl: ReviewReport = {
      ...mockReviewReport,
      task: { ...mockReviewReport.task, prUrl: 'https://github.com/owner/repo/pull/1' },
    };
    renderAt('/reviews/task-001', completedClient(reportWithUrl) as never, 0);

    await waitFor(() => expect(screen.getByText('PR 基本信息')).toBeInTheDocument());
    const link = screen.getByText('https://github.com/owner/repo/pull/1');
    expect(link.tagName).toBe('A');
    expect(link).toHaveAttribute('href', 'https://github.com/owner/repo/pull/1');
    expect(link).toHaveAttribute('target', '_blank');
  });
});

describe('History records page', () => {
  function historyClient(tasks: ReviewTask[] = mockTaskList) {
    return { listReviewTasks: vi.fn(async () => tasks) };
  }

  it('renders task list with all columns', async () => {
    renderAt('/history', historyClient());
    await waitFor(() => expect(screen.getByText('优化用户登录逻辑')).toBeInTheDocument());
    const rows = document.querySelectorAll('.history-row');
    expect(rows.length).toBeGreaterThanOrEqual(4);
    expect(screen.getByText('5')).toBeInTheDocument();
    const pills = document.querySelectorAll('.status-pill-task');
    expect(Array.from(pills).some((el) => el.textContent === '已完成')).toBe(true);
  });

  it('distinguishes pending, running, completed, and failed states', async () => {
    renderAt('/history', historyClient());
    await waitFor(() => expect(screen.getByText('优化用户登录逻辑')).toBeInTheDocument());
    const pills = document.querySelectorAll('.status-pill-task');
    const labels = Array.from(pills).map((el) => el.textContent);
    expect(labels).toContain('已完成'); expect(labels).toContain('分析中');
    expect(labels).toContain('待分析'); expect(labels).toContain('分析失败');
  });

  it('navigates to task detail on row click', async () => {
    const user = userEvent.setup();
    renderAt('/history', historyClient());
    await waitFor(() => expect(screen.getByText('优化用户登录逻辑')).toBeInTheDocument());
    await user.click(screen.getByText('优化用户登录逻辑'));
    expect(screen.getByRole('heading', { name: 'Review 报告详情' })).toBeInTheDocument();
    expect(screen.getByText(/task-001/)).toBeInTheDocument();
  });

  it('shows filter controls', async () => {
    renderAt('/history', historyClient());
    await waitFor(() => expect(screen.getByText('优化用户登录逻辑')).toBeInTheDocument());
    expect(screen.getByPlaceholderText('按项目筛选')).toBeInTheDocument();
    expect(screen.getAllByRole('combobox').length).toBe(2);
  });

  it('filters by project name', async () => {
    const listReviewTasks = vi.fn(async () => mockTaskList);
    renderAt('/history', { listReviewTasks });
    const projectInput = screen.getByPlaceholderText('按项目筛选');
    await userEvent.setup().type(projectInput, 'pay');
    await waitFor(() => expect(listReviewTasks).toHaveBeenCalledWith(expect.objectContaining({ projectName: 'pay' })));
  });

  it('filters by risk level', async () => {
    const listReviewTasks = vi.fn(async () => mockTaskList);
    renderAt('/history', { listReviewTasks });
    const riskSelect = screen.getAllByRole('combobox')[0];
    await userEvent.setup().selectOptions(riskSelect, 'high');
    await waitFor(() => expect(listReviewTasks).toHaveBeenCalledWith(expect.objectContaining({ riskLevel: 'high' })));
  });

  it('filters by status', async () => {
    const listReviewTasks = vi.fn(async () => mockTaskList);
    renderAt('/history', { listReviewTasks });
    const statusSelect = screen.getAllByRole('combobox')[1];
    await userEvent.setup().selectOptions(statusSelect, 'completed');
    await waitFor(() => expect(listReviewTasks).toHaveBeenCalledWith(expect.objectContaining({ status: 'completed' })));
  });

  it('shows empty state when no tasks', async () => {
    renderAt('/history', historyClient([]));
    await waitFor(() => expect(screen.getByText('暂无 Review 记录。')).toBeInTheDocument());
  });

  it('handles load errors', async () => {
    const listReviewTasks = vi.fn(async () => { throw new Error('Network error'); });
    renderAt('/history', { listReviewTasks });
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('加载历史记录失败'));
  });
});

describe('Settings page', () => {
  const mockSettings: SettingsResponse = {
    openai: { baseUri: 'https://api.openai.com/v1', apiKey: '***-729f', model: 'gpt-4' },
    anthropic: { baseUri: 'https://api.anthropic.com', apiKey: '***-83ab', model: 'claude-3-opus' },
    activeProvider: 'openai',
    mockEnabled: true,
    systemPrompt: '',
  };

  function settingsClient(overrides: Partial<{
    getSettings: () => Promise<SettingsResponse>;
    updateSettings: (req: SettingsResponse) => Promise<SettingsResponse>;
    testSettingsConnection: () => Promise<{ success: boolean; message: string }>;
  }> = {}) {
    return {
      createReviewTask: async () => { throw new Error('should not be called'); },
      getReviewTask: async () => { throw new Error('should not be called'); },
      getReviewReport: async () => { throw new Error('should not be called'); },
      listReviewTasks: async () => [],
      listReviewRules: async () => [],
      createReviewRule: async () => { throw new Error('should not be called'); },
      updateReviewRule: async () => { throw new Error('should not be called'); },
      enableReviewRule: async () => { throw new Error('should not be called'); },
      disableReviewRule: async () => { throw new Error('should not be called'); },
      deleteReviewRule: async () => { throw new Error('should not be called'); },
      updateIssueFeedback: async () => { throw new Error('should not be called'); },
      getDashboardMetrics: async () => ({ totalTasks: 0, tasksLast30Days: 0, totalIssues: 0, riskDistribution: { high: 0, medium: 0, low: 0 }, usefulRate: 0, falsePositiveRate: 0, adoptionRate: 0 }),
      getSettings: overrides.getSettings ?? (async () => mockSettings),
      updateSettings: overrides.updateSettings ?? (async () => mockSettings),
      testSettingsConnection: overrides.testSettingsConnection ?? (async () => ({ success: true, message: 'ok' })),
    };
  }

  it('renders both provider sections with fields', async () => {
    renderAt('/settings', settingsClient());
    await waitFor(() => expect(screen.getByText('运行模式')).toBeInTheDocument());
    expect(screen.getByText('Anthropic')).toBeInTheDocument();
    expect(screen.getAllByText('Base URI').length).toBe(2);
    expect(screen.getAllByText('API Key').length).toBe(2);
    expect(screen.getAllByText('Model').length).toBe(2);
    expect(screen.getAllByText('测试连接').length).toBe(2);
    expect(screen.getByText('保存配置')).toBeInTheDocument();
  });

  it('masks API keys on load showing last 4 chars', async () => {
    renderAt('/settings', settingsClient());
    await waitFor(() => expect(screen.getByText('运行模式')).toBeInTheDocument());
    const inputs = screen.getAllByPlaceholderText('sk-...');
    expect(inputs.length).toBe(2);
    expect((inputs[0] as HTMLInputElement).value).toBe('****729f');
    expect((inputs[1] as HTMLInputElement).value).toBe('****83ab');
  });

  it('reveals API key on focus', async () => {
    renderAt('/settings', settingsClient());
    await waitFor(() => expect(screen.getByText('运行模式')).toBeInTheDocument());
    const inputs = screen.getAllByPlaceholderText('sk-...');
    (inputs[0] as HTMLInputElement).focus();
    await waitFor(() => expect((inputs[0] as HTMLInputElement).value).toBe('***-729f'));
  });

  it('handles getSettings load error', async () => {
    const getSettings = vi.fn(async () => { throw new Error('Network error'); });
    renderAt('/settings', settingsClient({ getSettings }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('加载设置失败'));
  });

  it('saves settings with masked keys cleared to empty', async () => {
    const updateSettings = vi.fn(async (req: SettingsResponse) => req);
    renderAt('/settings', settingsClient({ updateSettings }));
    await waitFor(() => expect(screen.getByText('运行模式')).toBeInTheDocument());

    await userEvent.click(screen.getByText('保存配置'));
    await waitFor(() => expect(updateSettings).toHaveBeenCalledWith({
      openai: { baseUri: 'https://api.openai.com/v1', apiKey: '', model: 'gpt-4' },
      anthropic: { baseUri: 'https://api.anthropic.com', apiKey: '', model: 'claude-3-opus' },
      activeProvider: 'openai',
      mockEnabled: true,
      systemPrompt: '',
    }));
    expect(screen.getByText('已保存')).toBeInTheDocument();
  });

  it('shows save error on failure', async () => {
    const updateSettings = vi.fn(async () => { throw new ApiRequestError('保存失败', 500); });
    renderAt('/settings', settingsClient({ updateSettings }));
    await waitFor(() => expect(screen.getByText('运行模式')).toBeInTheDocument());

    await userEvent.click(screen.getByText('保存配置'));
    await waitFor(() => expect(screen.getByText('保存失败')).toBeInTheDocument());
  });

  it('tests connection with masked key omits apiKey', async () => {
    const testSettingsConnection = vi.fn(async () => ({ success: true, message: '连接成功' }));
    const realSettings = { ...mockSettings, mockEnabled: false };
    renderAt('/settings', settingsClient({ getSettings: async () => realSettings, testSettingsConnection }));
    await waitFor(() => expect(screen.getByText('运行模式')).toBeInTheDocument());

    const buttons = screen.getAllByText('测试连接');
    await userEvent.click(buttons[0]);
    await waitFor(() => expect(testSettingsConnection).toHaveBeenCalledWith({
      provider: 'openai',
      baseUri: 'https://api.openai.com/v1',
      model: 'gpt-4',
    }));
    expect(screen.getByText(/连接成功/)).toBeInTheDocument();
  });

  it('tests connection with user-typed key includes apiKey', async () => {
    const testSettingsConnection = vi.fn(async () => ({ success: true, message: '连接成功' }));
    const realSettings = { ...mockSettings, mockEnabled: false };
    renderAt('/settings', settingsClient({ getSettings: async () => realSettings, testSettingsConnection }));
    await waitFor(() => expect(screen.getByText('运行模式')).toBeInTheDocument());

    const inputs = screen.getAllByPlaceholderText('sk-...');
    (inputs[0] as HTMLInputElement).focus();
    await userEvent.clear(inputs[0]);
    await userEvent.type(inputs[0], 'sk-new-key');
    const buttons = screen.getAllByText('测试连接');
    await userEvent.click(buttons[0]);
    await waitFor(() => expect(testSettingsConnection).toHaveBeenCalledWith({
      provider: 'openai',
      baseUri: 'https://api.openai.com/v1',
      apiKey: 'sk-new-key',
      model: 'gpt-4',
    }));
  });

  it('tests connection and shows failure', async () => {
    const testSettingsConnection = vi.fn(async () => { throw new Error('Connection refused'); });
    const realSettings = { ...mockSettings, mockEnabled: false };
    renderAt('/settings', settingsClient({ getSettings: async () => realSettings, testSettingsConnection }));
    await waitFor(() => expect(screen.getByText('运行模式')).toBeInTheDocument());

    const buttons = screen.getAllByText('测试连接');
    await userEvent.click(buttons[0]);
    await waitFor(() => expect(screen.getByText(/连接失败/)).toBeInTheDocument());
  });

  it('renders mode toggle with Mock and Real API options', async () => {
    renderAt('/settings', settingsClient());
    await waitFor(() => expect(screen.getByText('运行模式')).toBeInTheDocument());
    expect(screen.getByText('运行模式')).toBeInTheDocument();
    expect(screen.getByText('Mock 模式')).toBeInTheDocument();
    expect(screen.getByText('真实 API')).toBeInTheDocument();
  });

  it('shows provider selector only in Real API mode', async () => {
    const realSettings = { ...mockSettings, mockEnabled: false };
    renderAt('/settings', settingsClient({ getSettings: async () => realSettings }));
    await waitFor(() => expect(screen.getByText('运行模式')).toBeInTheDocument());
    expect(screen.getByText('当前提供商')).toBeInTheDocument();

    await userEvent.click(screen.getByText('Mock 模式'));
    expect(screen.queryByText('当前提供商')).not.toBeInTheDocument();
  });

  it('disables test connection buttons in Mock mode', async () => {
    renderAt('/settings', settingsClient());
    await waitFor(() => expect(screen.getByText('运行模式')).toBeInTheDocument());
    const buttons = screen.getAllByText('测试连接');
    expect((buttons[0] as HTMLButtonElement).disabled).toBe(true);
    expect((buttons[1] as HTMLButtonElement).disabled).toBe(true);
    expect((buttons[0] as HTMLButtonElement).title).toBe('Mock 模式下不可测试连接');
  });

  it('renders system prompt textarea', async () => {
    renderAt('/settings', settingsClient());
    await waitFor(() => expect(screen.getByText('运行模式')).toBeInTheDocument());
    const textarea = screen.getByPlaceholderText('留空使用默认提示词');
    expect(textarea).toBeInTheDocument();
    expect(textarea.tagName).toBe('TEXTAREA');
    expect((textarea as HTMLTextAreaElement).value).toBe('');
  });

  it('binds system prompt value to textarea', async () => {
    const promptSettings = { ...mockSettings, systemPrompt: '自定义提示词内容' };
    renderAt('/settings', settingsClient({ getSettings: async () => promptSettings }));
    await waitFor(() => expect(screen.getByText('运行模式')).toBeInTheDocument());
    const textarea = screen.getByPlaceholderText('留空使用默认提示词') as HTMLTextAreaElement;
    expect(textarea.value).toBe('自定义提示词内容');
  });

  it('includes systemPrompt in save payload', async () => {
    const updateSettings = vi.fn(async (req: SettingsResponse) => req);
    const promptSettings = { ...mockSettings, systemPrompt: '修改后的提示词' };
    renderAt('/settings', settingsClient({ getSettings: async () => promptSettings, updateSettings }));
    await waitFor(() => expect(screen.getByText('运行模式')).toBeInTheDocument());

    const textarea = screen.getByPlaceholderText('留空使用默认提示词');
    await userEvent.clear(textarea);
    await userEvent.type(textarea, '新提示词');

    await userEvent.click(screen.getByText('保存配置'));
    await waitFor(() => expect(updateSettings).toHaveBeenCalledWith(expect.objectContaining({
      systemPrompt: '新提示词',
    })));
  });
});

describe('PR fetch on new review page', () => {
  const mockFetchResponse: FetchPrResponse = {
    title: 'Fetched PR Title',
    description: 'Fetched PR description',
    diffContent: 'diff --git a/test.ts b/test.ts',
    projectName: 'test-project',
    targetBranch: 'feature/test',
    developerName: 'Alice',
  };

  function prFetchClient(overrides: Partial<{
    createReviewTask: () => Promise<{ taskId: string; status: string }>;
    fetchPrInfo: (url: string) => Promise<FetchPrResponse>;
  }> = {}) {
    return {
      createReviewTask: overrides.createReviewTask ?? (async () => { throw new Error('should not be called'); }),
      fetchPrInfo: overrides.fetchPrInfo ?? (async () => mockFetchResponse),
      getReviewTask: async () => { throw new Error('should not be called'); },
      getReviewReport: async () => { throw new Error('should not be called'); },
      listReviewTasks: async () => [],
      listReviewRules: async () => [],
      createReviewRule: async () => { throw new Error('should not be called'); },
      updateReviewRule: async () => { throw new Error('should not be called'); },
      enableReviewRule: async () => { throw new Error('should not be called'); },
      disableReviewRule: async () => { throw new Error('should not be called'); },
      deleteReviewRule: async () => { throw new Error('should not be called'); },
      updateIssueFeedback: async () => { throw new Error('should not be called'); },
      getDashboardMetrics: async () => ({ totalTasks: 0, tasksLast30Days: 0, totalIssues: 0, riskDistribution: { high: 0, medium: 0, low: 0 }, usefulRate: 0, falsePositiveRate: 0, adoptionRate: 0 }),
      getSettings: async () => { throw new Error('should not be called'); },
      updateSettings: async () => { throw new Error('should not be called'); },
      testSettingsConnection: async () => { throw new Error('should not be called'); },
    };
  }

  it('renders URL input and fetch button', async () => {
    renderAt('/reviews/new', prFetchClient());
    expect(screen.getByPlaceholderText(/粘贴 GitHub PR URL/)).toBeInTheDocument();
    expect(screen.getByText('获取')).toBeInTheDocument();
  });

  it('populates form fields on successful fetch', async () => {
    const fetchPrInfo = vi.fn(async () => mockFetchResponse);
    renderAt('/reviews/new', prFetchClient({ fetchPrInfo }));

    const urlInput = screen.getByPlaceholderText(/粘贴 GitHub PR URL/);
    await userEvent.type(urlInput, 'https://github.com/owner/repo/pull/1');
    await userEvent.click(screen.getByText('获取'));

    await waitFor(() => expect(fetchPrInfo).toHaveBeenCalledWith('https://github.com/owner/repo/pull/1'));
    expect((screen.getByPlaceholderText('例如：优化用户登录逻辑') as HTMLInputElement).value).toBe('Fetched PR Title');
    expect(screen.getByDisplayValue('Fetched PR description')).toBeInTheDocument();
    expect(screen.getByDisplayValue('diff --git a/test.ts b/test.ts')).toBeInTheDocument();
    expect((screen.getByPlaceholderText('例如：user-center') as HTMLInputElement).value).toBe('test-project');
    expect((screen.getByPlaceholderText('例如：main') as HTMLInputElement).value).toBe('feature/test');
    expect((screen.getByPlaceholderText('例如：Alice') as HTMLInputElement).value).toBe('Alice');
  });

  it('shows error on fetch failure', async () => {
    const fetchPrInfo = vi.fn(async () => { throw new ApiRequestError('获取 PR 信息失败', 400); });
    renderAt('/reviews/new', prFetchClient({ fetchPrInfo }));

    const urlInput = screen.getByPlaceholderText(/粘贴 GitHub PR URL/);
    await userEvent.type(urlInput, 'https://github.com/owner/repo/pull/1');
    await userEvent.click(screen.getByText('获取'));

    await waitFor(() => expect(screen.getByText('获取 PR 信息失败')).toBeInTheDocument());
  });

  it('disables fetch button while loading', async () => {
    let resolve: (value: FetchPrResponse) => void;
    const fetchPrInfo = vi.fn(() => new Promise<FetchPrResponse>((r) => { resolve = r; }));
    renderAt('/reviews/new', prFetchClient({ fetchPrInfo }));

    const urlInput = screen.getByPlaceholderText(/粘贴 GitHub PR URL/);
    await userEvent.type(urlInput, 'https://github.com/owner/repo/pull/1');
    await userEvent.click(screen.getByText('获取'));

    expect(screen.getByText('获取中...')).toBeInTheDocument();
    const button = screen.getByText('获取中...') as HTMLButtonElement;
    expect(button.disabled).toBe(true);

    resolve!(mockFetchResponse);
    await waitFor(() => expect(screen.getByText('获取')).toBeInTheDocument());
  });
});

