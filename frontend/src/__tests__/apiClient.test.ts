import { describe, expect, it, vi } from 'vitest';
import { ApiClient, ApiRequestError, feedbackStatusLabels, issueTypeLabels, reviewTaskStatusLabels, riskLevelLabels } from '../api';
import type { DispatcherFetchResponse, FetchPrResponse, SettingsResponse } from '../api';
import { mockReviewReport, mockReviewRule } from '../test-fixtures/mockReview';

function jsonResponse(payload: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(payload), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' }
  });
}

describe('ApiClient', () => {
  it('serializes create Review requests and returns typed task responses', async () => {
    const fetcher = vi.fn(async () => jsonResponse({ task_id: 'task-001', status: 'pending' }));
    const client = new ApiClient({ baseUrl: '/api', fetcher });

    const result = await client.createReviewTask({
      prTitle: '优化用户登录逻辑',
      prDescription: '新增 token 刷新机制',
      projectName: 'user-center',
      targetBranch: 'main',
      developerName: 'Alice',
      diffContent: 'diff --git a/auth.ts b/auth.ts'
    });

    expect(result).toEqual({ taskId: 'task-001', status: 'pending' });
    expect(fetcher).toHaveBeenCalledWith('/api/review-tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Demo-Owner': 'demo-user' },
      body: JSON.stringify({
        pr_title: '优化用户登录逻辑',
        pr_description: '新增 token 刷新机制',
        project_name: 'user-center',
        target_branch: 'main',
        developer_name: 'Alice',
        diff_content: 'diff --git a/auth.ts b/auth.ts'
      })
    });
  });

  it('deserializes MockLLM-shaped report responses', async () => {
    const fetcher = vi.fn(async () => jsonResponse({
      id: mockReviewReport.id,
      task: {
        id: 'task-001',
        pr_title: '优化用户登录逻辑',
        pr_description: '新增 token 刷新机制',
        project_name: 'user-center',
        target_branch: 'main',
        developer_name: 'Alice',
        status: 'completed',
        risk_level: 'high',
        issue_count: 2,
        created_by: 'reviewer-001',
        created_at: '2026-05-29T10:00:00.000Z',
        updated_at: '2026-05-29T10:03:00.000Z'
      },
      summary: {
        purpose: '新增登录 token 刷新流程。',
        changed_modules: ['认证模块'],
        key_files: ['src/auth/AuthService.ts'],
        business_impact: '影响用户登录态续期。',
        test_or_security_notes: '涉及认证逻辑，缺少异常场景测试。'
      },
      risk: { level: 'high', reasons: ['修改认证核心流程'] },
      issue_stats: { total: 1, high: 1, medium: 0, low: 0, rule_hits: 0 },
      issues: [
        {
          id: 'issue-001',
          task_id: 'task-001',
          report_id: 'report-001',
          title: '缺少 token 刷新失败处理',
          type: 'exception',
          severity: 'high',
          description: '刷新失败时没有清理登录状态。',
          location: { file_path: 'src/auth/AuthService.ts', line_hint: 'L42-L58', code_snippet: 'refreshToken();' },
          suggestion: '在刷新失败时清理登录态并返回可解释错误。',
          confidence: 'high',
          matched_rule_ids: [],
          feedback_status: 'none',
          created_at: '2026-05-29T10:03:00.000Z'
        }
      ],
      created_at: '2026-05-29T10:03:00.000Z'
    }));
    const client = new ApiClient({ fetcher });

    const report = await client.getReviewReport('task-001');

    expect(report.task.prTitle).toBe('优化用户登录逻辑');
    expect(report.summary.changedModules).toEqual(['认证模块']);
    expect(report.issueStats.ruleHits).toBe(0);
    expect(report.issues[0].location.filePath).toBe('src/auth/AuthService.ts');
  });

  it('supports rules, filters, and feedback endpoints through typed functions', async () => {
    const fetcher = vi.fn(async () => jsonResponse(mockReviewRule));
    const client = new ApiClient({ baseUrl: '/api', fetcher });

    await client.listReviewTasks({ projectName: 'user-center', riskLevel: 'high', status: 'completed' });
    await client.createReviewRule({ name: mockReviewRule.name, description: mockReviewRule.description, type: 'test', severity: 'medium', enabled: true });
    await client.updateIssueFeedback('issue-001', { feedbackStatus: 'false_positive', comment: '这是误报' });

    expect(fetcher).toHaveBeenNthCalledWith(1, '/api/review-tasks?project_name=user-center&risk_level=high&status=completed', expect.any(Object));
    expect(fetcher).toHaveBeenNthCalledWith(2, '/api/review-rules', expect.objectContaining({ method: 'POST' }));
    expect(fetcher).toHaveBeenNthCalledWith(3, '/api/review-issues/issue-001/feedback', expect.objectContaining({
      method: 'PATCH',
      body: JSON.stringify({ feedback_status: 'false_positive', comment: '这是误报' })
    }));
  });

  it('raises user-readable request errors from failed responses', async () => {
    const fetcher = vi.fn(async () => jsonResponse({ detail: 'PR 标题不能为空。' }, { status: 400 }));
    const client = new ApiClient({ fetcher });

    await expect(client.getReviewTask('missing')).rejects.toMatchObject({
      name: 'ApiRequestError',
      status: 400,
      message: 'PR 标题不能为空。'
    } satisfies Partial<ApiRequestError>);
  });

  it('provides Chinese labels for English API enum values', () => {
    expect(reviewTaskStatusLabels.running).toBe('分析中');
    expect(riskLevelLabels.high).toBe('高风险');
    expect(issueTypeLabels.test_missing).toBe('测试缺失');
    expect(feedbackStatusLabels.false_positive).toBe('误报');
  });

  it('fetches settings response with camelCase keys', async () => {
    const fetcher = vi.fn(async () => jsonResponse({
      openai: { base_uri: 'https://api.openai.com/v1', api_key: 'sk-abc', model: 'gpt-4' },
      anthropic: { base_uri: 'https://api.anthropic.com', api_key: 'sk-ant-xyz', model: 'claude-3-opus' },
      active_provider: 'openai',
      mock_enabled: true,
      system_prompt: '自定义提示',
    }));
    const client = new ApiClient({ fetcher });

    const settings = await client.getSettings();

    expect(settings.openai.baseUri).toBe('https://api.openai.com/v1');
    expect(settings.openai.apiKey).toBe('sk-abc');
    expect(settings.anthropic.baseUri).toBe('https://api.anthropic.com');
    expect(settings.anthropic.apiKey).toBe('sk-ant-xyz');
    expect(settings.activeProvider).toBe('openai');
    expect(settings.mockEnabled).toBe(true);
    expect(settings.systemPrompt).toBe('自定义提示');
  });

  it('serializes updateSettings with snake_case keys', async () => {
    const fetcher = vi.fn(async () => jsonResponse({
      openai: { base_uri: 'https://api.openai.com/v1', api_key: 'sk-abc', model: 'gpt-4' },
      anthropic: { base_uri: 'https://api.anthropic.com', api_key: 'sk-ant-xyz', model: 'claude-3-opus' },
      active_provider: 'openai',
      mock_enabled: true,
    }));
    const client = new ApiClient({ baseUrl: '/api', fetcher });

    const payload: SettingsResponse = {
      openai: { baseUri: 'https://api.openai.com/v1', apiKey: 'sk-abc', model: 'gpt-4' },
      anthropic: { baseUri: 'https://api.anthropic.com', apiKey: 'sk-ant-xyz', model: 'claude-3-opus' },
      activeProvider: 'openai',
      mockEnabled: true,
      systemPrompt: '自定义提示',
    };
    await client.updateSettings(payload);

    expect(fetcher).toHaveBeenCalledWith('/api/settings', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({
        openai: { base_uri: 'https://api.openai.com/v1', api_key: 'sk-abc', model: 'gpt-4' },
        anthropic: { base_uri: 'https://api.anthropic.com', api_key: 'sk-ant-xyz', model: 'claude-3-opus' },
        active_provider: 'openai',
        mock_enabled: true,
        system_prompt: '自定义提示',
      }),
    }));
  });

  it('sends test connection request and returns result', async () => {
    const fetcher = vi.fn(async () => jsonResponse({ success: true, message: '连接成功' }));
    const client = new ApiClient({ baseUrl: '/api', fetcher });

    const result = await client.testSettingsConnection({
      provider: 'openai',
      baseUri: 'https://api.openai.com/v1',
      apiKey: 'sk-test',
      model: 'gpt-4',
    });

    expect(result).toEqual({ success: true, message: '连接成功' });
    expect(fetcher).toHaveBeenCalledWith('/api/settings/test', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        provider: 'openai',
        base_uri: 'https://api.openai.com/v1',
        api_key: 'sk-test',
        model: 'gpt-4',
      }),
    }));
  });

  it('handles settings load error with readable message', async () => {
    const fetcher = vi.fn(async () => jsonResponse({ detail: '配置加载失败' }, { status: 500 }));
    const client = new ApiClient({ fetcher });

    await expect(client.getSettings()).rejects.toMatchObject({
      name: 'ApiRequestError',
      status: 500,
      message: '配置加载失败',
    } satisfies Partial<ApiRequestError>);
  });

  it('fetches PR info and returns deserialized response', async () => {
    const fetcher = vi.fn(async () => jsonResponse({
      title: 'PR Title',
      description: 'PR Desc',
      diff_content: 'diff --git a/file.ts b/file.ts',
      project_name: 'my-project',
      target_branch: 'main',
      developer_name: 'Bob',
    }));
    const client = new ApiClient({ baseUrl: '/api', fetcher });

    const result = await client.fetchPrInfo('https://github.com/owner/repo/pull/1');

    expect(result).toEqual({
      title: 'PR Title',
      description: 'PR Desc',
      diffContent: 'diff --git a/file.ts b/file.ts',
      projectName: 'my-project',
      targetBranch: 'main',
      developerName: 'Bob',
    } satisfies FetchPrResponse);
    expect(fetcher).toHaveBeenCalledWith('/api/pr-fetch', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ url: 'https://github.com/owner/repo/pull/1' }),
    }));
  });

  it('handles PR fetch error', async () => {
    const fetcher = vi.fn(async () => jsonResponse({ detail: 'PR 不存在' }, { status: 404 }));
    const client = new ApiClient({ fetcher });

    await expect(client.fetchPrInfo('https://github.com/a/b/pull/99')).rejects.toMatchObject({
      name: 'ApiRequestError',
      status: 404,
      message: 'PR 不存在',
    } satisfies Partial<ApiRequestError>);
  });

  it('calls dispatcher fetch endpoint and returns deserialized response', async () => {
    const fetcher = vi.fn(async () => jsonResponse({
      api_key: 'sk-dispatcher-key-001',
      base_uri: 'https://api.openai.com/v1',
      model: 'gpt-4o',
      openai_model: 'gpt-4o',
      anthropic_model: 'claude-sonnet-4-6',
      expires_in: 3600,
    }));
    const client = new ApiClient({ baseUrl: '/api', fetcher });

    const result = await client.fetchDispatcherCredentials('https://dispatcher.example.com/keys');

    expect(result).toEqual({
      apiKey: 'sk-dispatcher-key-001',
      baseUri: 'https://api.openai.com/v1',
      model: 'gpt-4o',
      openaiModel: 'gpt-4o',
      anthropicModel: 'claude-sonnet-4-6',
      expiresIn: 3600,
    } satisfies DispatcherFetchResponse);
    expect(fetcher).toHaveBeenCalledWith('/api/settings/dispatcher-fetch', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ url: 'https://dispatcher.example.com/keys' }),
    }));
  });

  it('handles dispatcher fetch error', async () => {
    const fetcher = vi.fn(async () => jsonResponse({ detail: '分发器不可达' }, { status: 502 }));
    const client = new ApiClient({ fetcher });

    await expect(client.fetchDispatcherCredentials('https://bad.example.com')).rejects.toMatchObject({
      name: 'ApiRequestError',
      status: 502,
      message: '分发器不可达',
    } satisfies Partial<ApiRequestError>);
  });
});
