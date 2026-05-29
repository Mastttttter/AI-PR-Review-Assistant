import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { App } from '../App';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>
  );
}

describe('application shell routes', () => {
  it.each([
    ['/', '首页 / 工作台'],
    ['/reviews/new', '新建 Review'],
    ['/history', '历史记录'],
    ['/rules', '规则配置'],
    ['/reviews/task-123', 'Review 报告详情']
  ])('renders %s route', (path, heading) => {
    renderAt(path);
    expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument();
  });

  it('shows a safe fallback for unknown routes', () => {
    renderAt('/missing/page');
    expect(screen.getByRole('heading', { name: '页面不存在' })).toBeInTheDocument();
    expect(screen.getByText('当前路径没有对应页面，请通过左侧导航返回 MVP 功能入口。')).toBeInTheDocument();
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

  it('includes loading and error shells on the report route', () => {
    renderAt('/reviews/task-123');
    expect(screen.getByRole('status')).toHaveTextContent('报告生成中');
    expect(screen.getByRole('alert')).toHaveTextContent('如果报告生成失败');
  });
});
