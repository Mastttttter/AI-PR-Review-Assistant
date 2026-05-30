import type {
  CreateReviewTaskRequest,
  CreateReviewTaskResponse,
  DashboardResponse,
  FeedbackRequest,
  FeedbackResponse,
  FetchPrRequest,
  FetchPrResponse,
  ProviderConfig,
  ReviewReport,
  ReviewRule,
  ReviewTask,
  ReviewTaskListQuery,
  SettingsResponse,
  TestConnectionRequest,
  TestConnectionResponse,
  UpsertReviewRuleRequest
} from './types';

type RequestBody = object | undefined;

type ApiClientOptions = {
  baseUrl?: string;
  fetcher?: typeof fetch;
};

export class ApiRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly detail?: unknown
  ) {
    super(message);
    this.name = 'ApiRequestError';
  }
}

function toSnakeCase(value: string): string {
  return value.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
}

function toCamelCase(value: string): string {
  return value.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase());
}

function transformKeys(value: unknown, transform: (key: string) => string): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => transformKeys(item, transform));
  }

  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [transform(key), transformKeys(item, transform)])
    );
  }

  return value;
}

function buildQuery(query?: ReviewTaskListQuery): string {
  if (!query) {
    return '';
  }

  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value) {
      params.set(toSnakeCase(key), value);
    }
  });

  const serialized = params.toString();
  return serialized ? `?${serialized}` : '';
}

async function parseResponse(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return undefined;
  }

  const text = await response.text();
  if (!text) {
    return undefined;
  }

  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

function readableErrorMessage(status: number, payload: unknown): string {
  if (payload && typeof payload === 'object') {
    const record = payload as Record<string, unknown>;
    const detail = record.detail ?? record.message ?? record.error;
    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }
  }

  if (status === 400) return '提交内容不符合要求，请检查必填字段和格式。';
  if (status === 401) return '登录状态已失效，请重新登录后再试。';
  if (status === 403) return '当前账号无权访问该 Review 资源。';
  if (status === 404) return '没有找到对应的 Review 资源。';
  if (status >= 500) return '服务暂时不可用，请稍后重试。';
  return '请求失败，请稍后重试。';
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly fetcher: typeof fetch;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? '/api';
    this.fetcher = options.fetcher ?? fetch.bind(window);
  }

  async createReviewTask(request: CreateReviewTaskRequest): Promise<CreateReviewTaskResponse> {
    return this.request<CreateReviewTaskResponse>('/review-tasks', { method: 'POST', body: request });
  }

  async listReviewTasks(query?: ReviewTaskListQuery): Promise<ReviewTask[]> {
    return this.request<ReviewTask[]>(`/review-tasks${buildQuery(query)}`);
  }

  async getReviewTask(taskId: string): Promise<ReviewTask> {
    return this.request<ReviewTask>(`/review-tasks/${encodeURIComponent(taskId)}`);
  }

  async deleteReviewTask(taskId: string): Promise<void> {
    await this.request<void>(`/review-tasks/${encodeURIComponent(taskId)}`, { method: 'DELETE' });
  }

  async rerunReviewTask(taskId: string): Promise<CreateReviewTaskResponse> {
    return this.request<CreateReviewTaskResponse>(`/review-tasks/${encodeURIComponent(taskId)}/rerun`, { method: 'POST' });
  }

  async getReviewReport(taskId: string): Promise<ReviewReport> {
    return this.request<ReviewReport>(`/review-tasks/${encodeURIComponent(taskId)}/report`);
  }

  async listReviewRules(): Promise<ReviewRule[]> {
    return this.request<ReviewRule[]>('/review-rules');
  }

  async createReviewRule(request: UpsertReviewRuleRequest): Promise<ReviewRule> {
    return this.request<ReviewRule>('/review-rules', { method: 'POST', body: request });
  }

  async updateReviewRule(ruleId: string, request: UpsertReviewRuleRequest): Promise<ReviewRule> {
    return this.request<ReviewRule>(`/review-rules/${encodeURIComponent(ruleId)}`, { method: 'PUT', body: request });
  }

  async enableReviewRule(ruleId: string): Promise<ReviewRule> {
    return this.request<ReviewRule>(`/review-rules/${encodeURIComponent(ruleId)}/enable`, { method: 'PATCH' });
  }

  async disableReviewRule(ruleId: string): Promise<ReviewRule> {
    return this.request<ReviewRule>(`/review-rules/${encodeURIComponent(ruleId)}/disable`, { method: 'PATCH' });
  }

  async deleteReviewRule(ruleId: string): Promise<void> {
    await this.request<void>(`/review-rules/${encodeURIComponent(ruleId)}`, { method: 'DELETE' });
  }

  async getDashboardMetrics(): Promise<DashboardResponse> {
    return this.request<DashboardResponse>('/metrics/dashboard');
  }

  async updateIssueFeedback(issueId: string, request: FeedbackRequest): Promise<FeedbackResponse> {
    return this.request<FeedbackResponse>(`/review-issues/${encodeURIComponent(issueId)}/feedback`, { method: 'PATCH', body: request });
  }

  async getSettings(): Promise<SettingsResponse> {
    return this.request<SettingsResponse>('/settings');
  }

  async updateSettings(request: SettingsResponse): Promise<SettingsResponse> {
    return this.request<SettingsResponse>('/settings', { method: 'PUT', body: request });
  }

  async testSettingsConnection(request: TestConnectionRequest): Promise<TestConnectionResponse> {
    return this.request<TestConnectionResponse>('/settings/test', { method: 'POST', body: request });
  }

  async fetchPrInfo(url: string): Promise<FetchPrResponse> {
    return this.request<FetchPrResponse>('/pr-fetch', { method: 'POST', body: { url } satisfies FetchPrRequest });
  }

  private async request<T>(path: string, init: { method?: string; body?: RequestBody } = {}): Promise<T> {
    const response = await this.fetcher(`${this.baseUrl}${path}`, {
      method: init.method ?? 'GET',
      headers: { 'X-Demo-Owner': 'demo-user', ...(init.body ? { 'Content-Type': 'application/json' } : {}) },
      body: init.body ? JSON.stringify(transformKeys(init.body, toSnakeCase)) : undefined
    });

    const payload = await parseResponse(response);
    if (!response.ok) {
      throw new ApiRequestError(readableErrorMessage(response.status, payload), response.status, payload);
    }

    return transformKeys(payload, toCamelCase) as T;
  }
}

export const apiClient = new ApiClient();
