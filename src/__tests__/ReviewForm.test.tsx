import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { App } from '../App';
import type { CreateReviewTaskRequest, CreateReviewTaskResponse, ReviewReport, ReviewTask, ReviewTaskListQuery } from '../api';

function neverPoll(_id: string): Promise<ReviewTask> {
  throw new Error('polling should not be triggered from this test');
}
function neverReport(_id: string): Promise<ReviewReport> {
  throw new Error('report fetch should not be triggered from this test');
}
async function neverTasks(_query?: ReviewTaskListQuery): Promise<ReviewTask[]> {
  throw new Error('history should not be triggered from this test');
}
function neverRules(): Promise<never> {
  throw new Error('rules should not be triggered from this test');
}
function neverRuleMutation(..._args: unknown[]): Promise<never> {
  throw new Error('rule mutation should not be triggered from this test');
}

function renderForm(createReviewTask = vi.fn<(_: CreateReviewTaskRequest) => Promise<CreateReviewTaskResponse>>()) {
  const client = {
    createReviewTask,
    getReviewTask: neverPoll,
    getReviewReport: neverReport,
    listReviewTasks: neverTasks,
    listReviewRules: neverRules,
    createReviewRule: neverRuleMutation,
    updateReviewRule: neverRuleMutation,
    enableReviewRule: neverRuleMutation,
    disableReviewRule: neverRuleMutation,
    deleteReviewRule: neverRuleMutation,
  };
  render(
    <MemoryRouter initialEntries={['/reviews/new']}>
      <App client={client} />
    </MemoryRouter>
  );
  return { createReviewTask };
}

describe('new Review task form', () => {
  it('requires PR title and diff before submission', async () => {
    const user = userEvent.setup();
    const { createReviewTask } = renderForm();

    await user.click(screen.getByRole('button', { name: '开始 Review' }));

    expect(await screen.findByText('PR 标题不能为空。')).toBeInTheDocument();
    expect(screen.getByText('代码变更内容不能为空。')).toBeInTheDocument();
    expect(createReviewTask).not.toHaveBeenCalled();
  });

  it('prevents diff input over 50k characters', async () => {
    const user = userEvent.setup();
    const { createReviewTask } = renderForm();

    await user.type(screen.getByLabelText(/PR 标题/), '优化登录逻辑');
    fireEvent.change(screen.getByLabelText(/代码变更内容/), { target: { value: 'a'.repeat(50_001) } });
    await user.click(screen.getByRole('button', { name: '开始 Review' }));

    expect(await screen.findByText('代码变更内容不能超过 50,000 个字符。')).toBeInTheDocument();
    expect(screen.getByText('50,001 / 50,000')).toHaveClass('over-limit');
    expect(createReviewTask).not.toHaveBeenCalled();
  });

  it('submits typed Review data and routes to the task report flow', async () => {
    const user = userEvent.setup();
    let resolveSubmit: (value: CreateReviewTaskResponse) => void = () => undefined;
    const submitPromise = new Promise<CreateReviewTaskResponse>((resolve) => {
      resolveSubmit = resolve;
    });
    const createReviewTask = vi.fn(() => submitPromise);
    renderForm(createReviewTask);

    await user.type(screen.getByLabelText(/PR 标题/), '优化用户登录逻辑');
    await user.type(screen.getByLabelText(/所属项目/), 'user-center');
    await user.type(screen.getByLabelText(/目标分支/), 'main');
    await user.type(screen.getByLabelText(/开发者名称/), 'Alice');
    await user.type(screen.getByLabelText(/PR 描述/), '新增 token 刷新机制');
    await user.type(screen.getByLabelText(/代码变更内容/), 'diff --git a/auth.ts b/auth.ts');
    await user.click(screen.getByRole('button', { name: '开始 Review' }));

    expect(screen.getByRole('status')).toHaveTextContent('正在创建 Review 任务');
    await waitFor(() => expect(createReviewTask).toHaveBeenCalledWith({
      prTitle: '优化用户登录逻辑',
      prDescription: '新增 token 刷新机制',
      projectName: 'user-center',
      targetBranch: 'main',
      developerName: 'Alice',
      diffContent: 'diff --git a/auth.ts b/auth.ts'
    }));
    resolveSubmit({ taskId: 'task-abc', status: 'pending' });
    expect(await screen.findByRole('heading', { name: 'Review 报告详情' })).toBeInTheDocument();
    expect(screen.getByText(/task-abc/)).toBeInTheDocument();
  });

  it('surfaces user-readable submit failures without leaving the form', async () => {
    const user = userEvent.setup();
    const createReviewTask = vi.fn(async () => {
      throw new Error('服务暂时不可用，请稍后重试。');
    });
    renderForm(createReviewTask);

    await user.type(screen.getByLabelText(/PR 标题/), '优化用户登录逻辑');
    await user.type(screen.getByLabelText(/代码变更内容/), 'diff --git a/auth.ts b/auth.ts');
    await user.click(screen.getByRole('button', { name: '开始 Review' }));

    expect(await screen.findByText('创建 Review 任务失败，请稍后重试。')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '新建 Review' })).toBeInTheDocument();
  });
});
