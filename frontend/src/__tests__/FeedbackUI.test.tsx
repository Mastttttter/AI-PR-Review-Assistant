import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { App } from '../App';
import { ApiRequestError } from '../api';
import type { DashboardResponse, FeedbackResponse, ReviewReport, ReviewTask, ReviewTaskListQuery } from '../api';
import { mockReviewReport, mockReviewTask } from '../test-fixtures/mockReview';

function neverCalled(): Promise<never> {
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

async function neverSettings(): Promise<never> {
  throw new Error('should not be called');
}

function createFeedbackClient(overrides: Partial<{
  updateIssueFeedback: (issueId: string, request: { feedbackStatus: string; comment?: string }) => Promise<FeedbackResponse>;
}> = {}) {
  const getReviewTask = vi.fn(async () => ({ ...mockReviewTask, status: 'completed' as const }));
  const getReviewReport = vi.fn(async () => mockReviewReport);
  const updateIssueFeedback = overrides.updateIssueFeedback ?? vi.fn(async (issueId: string, request: { feedbackStatus: string; comment?: string }): Promise<FeedbackResponse> => ({
    issueId,
    taskId: mockReviewTask.id,
    feedbackStatus: request.feedbackStatus as FeedbackResponse['feedbackStatus'],
    updatedAt: '2026-05-30T12:00:00.000Z',
  }));

  return {
    createReviewTask: neverCalled,
    getReviewTask,
    getReviewReport,
    listReviewTasks: neverTasks,
    listReviewRules: emptyRules,
    createReviewRule: neverRuleMutation,
    updateReviewRule: neverRuleMutation,
    enableReviewRule: neverRuleMutation,
    disableReviewRule: neverRuleMutation,
    deleteReviewRule: neverRuleMutation,
    updateIssueFeedback,
    getDashboardMetrics: async (): Promise<DashboardResponse> => ({ totalTasks: 0, tasksLast30Days: 0, totalIssues: 0, riskDistribution: { high: 0, medium: 0, low: 0 }, usefulRate: 0, falsePositiveRate: 0, adoptionRate: 0 }),
    getSettings: neverSettings,
    updateSettings: neverSettings,
    testSettingsConnection: neverSettings,
  };
}

function renderReport(client: ReturnType<typeof createFeedbackClient>) {
  return render(
    <MemoryRouter initialEntries={['/reviews/task-001']}>
      <App client={client as never} pollIntervalMs={0} />
    </MemoryRouter>
  );
}

describe('User feedback submission UI', () => {
  it('renders feedback controls on each issue', async () => {
    const client = createFeedbackClient();
    renderReport(client);

    await waitFor(() => expect(screen.getByText('问题列表')).toBeInTheDocument());
    const feedbackLabels = screen.getAllByText('反馈:');
    expect(feedbackLabels.length).toBeGreaterThanOrEqual(1);
  });

  it('shows all five feedback options', async () => {
    const client = createFeedbackClient();
    renderReport(client);

    await waitFor(() => expect(screen.getByText('问题列表')).toBeInTheDocument());
    expect(screen.getAllByText('有用').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('无用').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('误报').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('已采纳').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('暂不处理').length).toBeGreaterThanOrEqual(1);
  });

  it('submits feedback and updates UI immediately', async () => {
    const updateIssueFeedback = vi.fn(async (issueId: string, request: { feedbackStatus: string; comment?: string }): Promise<FeedbackResponse> => ({
      issueId,
      taskId: mockReviewTask.id,
      feedbackStatus: 'adopted' as const,
      updatedAt: '2026-05-30T12:00:00.000Z',
    }));
    const client = createFeedbackClient({ updateIssueFeedback });
    renderReport(client);

    await waitFor(() => expect(screen.getByText('问题列表')).toBeInTheDocument());

    const adoptedButtons = screen.getAllByText('已采纳');
    const firstAdoptedButton = adoptedButtons.find(el => el.tagName === 'BUTTON');
    expect(firstAdoptedButton).toBeTruthy();

    await userEvent.click(firstAdoptedButton!);

    await waitFor(() => {
      expect(updateIssueFeedback).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ feedbackStatus: 'adopted' })
      );
    });
  });

  it('shows loading state during submission', async () => {
    let resolvePromise: (value: FeedbackResponse) => void;
    const updateIssueFeedback = vi.fn(() => new Promise<FeedbackResponse>((resolve) => {
      resolvePromise = resolve;
    }));
    const client = createFeedbackClient({ updateIssueFeedback });
    renderReport(client);

    await waitFor(() => expect(screen.getByText('问题列表')).toBeInTheDocument());

    const usefulButtons = screen.getAllByText('有用');
    const firstUsefulButton = usefulButtons.find(el => el.tagName === 'BUTTON' && !el.classList.contains('active'));
    expect(firstUsefulButton).toBeTruthy();

    await userEvent.click(firstUsefulButton!);

    await waitFor(() => {
      const submittingButton = screen.getAllByText('提交中...').find(el => el.closest('.feedback-option'));
      expect(submittingButton).toBeTruthy();
    });

    resolvePromise!({
      issueId: 'issue-001',
      taskId: mockReviewTask.id,
      feedbackStatus: 'useful',
      updatedAt: '2026-05-30T12:00:00.000Z',
    });
  });

  it('highlights the currently selected feedback option', async () => {
    const client = createFeedbackClient();
    renderReport(client);

    await waitFor(() => expect(screen.getByText('问题列表')).toBeInTheDocument());

    const usefulButtons = screen.getAllByText('有用');
    const activeButton = usefulButtons.find(el => el.closest('.feedback-option.active'));
    expect(activeButton).toBeTruthy();
  });

  it('handles submission errors gracefully', async () => {
    const updateIssueFeedback = vi.fn(async () => {
      throw new ApiRequestError('网络错误', 500);
    });
    const client = createFeedbackClient({ updateIssueFeedback });
    renderReport(client);

    await waitFor(() => expect(screen.getByText('问题列表')).toBeInTheDocument());

    const uselessButtons = screen.getAllByText('无用');
    const firstUselessButton = uselessButtons.find(el => el.tagName === 'BUTTON');
    expect(firstUselessButton).toBeTruthy();

    await userEvent.click(firstUselessButton!);

    await waitFor(() => {
      const errorMessage = screen.getByText('网络错误');
      expect(errorMessage).toBeInTheDocument();
    });
  });

  it('preserves previous feedback status on error', async () => {
    const updateIssueFeedback = vi.fn(async () => {
      throw new ApiRequestError('网络错误', 500);
    });
    const client = createFeedbackClient({ updateIssueFeedback });
    renderReport(client);

    await waitFor(() => expect(screen.getByText('问题列表')).toBeInTheDocument());

    const usefulButtonsBefore = screen.getAllByText('有用');
    const activeBefore = usefulButtonsBefore.find(el => el.closest('.feedback-option.active'));
    expect(activeBefore).toBeTruthy();

    const uselessButtons = screen.getAllByText('无用');
    const firstUselessButton = uselessButtons.find(el => el.tagName === 'BUTTON');
    await userEvent.click(firstUselessButton!);

    await waitFor(() => expect(screen.getByText('网络错误')).toBeInTheDocument());

    const usefulButtonsAfter = screen.getAllByText('有用');
    const activeAfter = usefulButtonsAfter.find(el => el.closest('.feedback-option.active'));
    expect(activeAfter).toBeTruthy();
  });
});
