import type { ReviewReport, ReviewRule, ReviewTask } from '../api';

export const mockReviewTask: ReviewTask = {
  id: 'task-001',
  prTitle: '优化用户登录逻辑',
  prDescription: '新增 token 刷新机制',
  projectName: 'user-center',
  targetBranch: 'main',
  developerName: 'Alice',
  status: 'completed',
  riskLevel: 'high',
  issueCount: 2,
  createdBy: 'reviewer-001',
  createdAt: '2026-05-29T10:00:00.000Z',
  updatedAt: '2026-05-29T10:03:00.000Z'
};

export const mockReviewRule: ReviewRule = {
  id: 'rule-001',
  name: '修改核心逻辑必须补充测试',
  description: '修改登录、支付、权限等核心逻辑时必须补充测试。',
  type: 'test',
  severity: 'medium',
  enabled: true,
  createdAt: '2026-05-29T09:00:00.000Z',
  updatedAt: '2026-05-29T09:00:00.000Z'
};

export const mockReviewReport: ReviewReport = {
  id: 'report-001',
  task: mockReviewTask,
  summary: {
    purpose: '新增登录 token 刷新流程。',
    changedModules: ['认证模块'],
    keyFiles: ['src/auth/AuthService.ts'],
    businessImpact: '影响用户登录态续期。',
    testOrSecurityNotes: '涉及认证逻辑，缺少异常场景测试。'
  },
  risk: {
    level: 'high',
    reasons: ['修改认证核心流程', '未发现对应测试']
  },
  issueStats: {
    total: 2,
    high: 1,
    medium: 1,
    low: 0,
    ruleHits: 1
  },
  issues: [
    {
      id: 'issue-001',
      taskId: 'task-001',
      reportId: 'report-001',
      title: '缺少 token 刷新失败处理',
      type: 'exception',
      severity: 'high',
      description: '刷新失败时没有清理登录状态，可能导致前端继续使用失效 token。',
      location: {
        filePath: 'src/auth/AuthService.ts',
        lineHint: 'L42-L58',
        codeSnippet: 'refreshToken();'
      },
      suggestion: '在刷新失败时清理登录态并返回可解释错误。',
      confidence: 'high',
      matchedRuleIds: [],
      feedbackStatus: 'none',
      createdAt: '2026-05-29T10:03:00.000Z'
    },
    {
      id: 'issue-002',
      taskId: 'task-001',
      reportId: 'report-001',
      title: '核心逻辑缺少测试',
      type: 'test_missing',
      severity: 'medium',
      description: '认证流程变化但没有新增成功和失败路径测试。',
      location: {},
      suggestion: '补充 token 刷新成功、失败和过期场景测试。',
      confidence: 'medium',
      matchedRuleIds: ['rule-001'],
      feedbackStatus: 'useful',
      createdAt: '2026-05-29T10:03:00.000Z'
    }
  ],
  createdAt: '2026-05-29T10:03:00.000Z'
};
