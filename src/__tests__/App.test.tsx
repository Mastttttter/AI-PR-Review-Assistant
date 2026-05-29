import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { App } from '../App';
import type { ReviewReport, ReviewTask } from '../api';
import { mockReviewReport, mockReviewTask } from '../test-fixtures/mockReview';

async function neverCalled(): Promise<never> {
  throw new Error('should not be called');
}

function neverReport(_id: string): Promise<ReviewReport> {
  throw new Error('should not be called');
}

function renderAt(path: string, client = { createReviewTask: neverCalled, getReviewTask: neverCalled, getReviewReport: neverCalled }, pollIntervalMs?: number) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App client={client} pollIntervalMs={pollIntervalMs} />
    </MemoryRouter>
  );
}

describe('application shell routes', () => {
  it.each([
    ['/', '首页 / 工作台'],
    ['/reviews/new', '新建 Review'],
    ['/history', '历史记录'],
    ['/rules', '规则配置'],
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

    await user.click(screen.getByRole('link', { name: '报告详情' }));
    expect(screen.getByRole('heading', { name: 'Review 报告详情' })).toBeInTheDocument();
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
