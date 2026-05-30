import type { ConfidenceLevel, FeedbackStatus, IssueSeverity, IssueType, ReviewTaskStatus, RiskLevel, RuleType } from './types';

export const reviewTaskStatusLabels: Record<ReviewTaskStatus, string> = {
  pending: '待分析',
  running: '分析中',
  completed: '已完成',
  failed: '分析失败',
  deleted: '已删除'
};

export const riskLevelLabels: Record<RiskLevel, string> = {
  low: '低风险',
  medium: '中风险',
  high: '高风险'
};

export const issueSeverityLabels: Record<IssueSeverity, string> = {
  low: '低',
  medium: '中',
  high: '高'
};

export const issueTypeLabels: Record<IssueType, string> = {
  logic: '逻辑问题',
  exception: '异常处理问题',
  security: '安全问题',
  performance: '性能问题',
  maintainability: '可维护性问题',
  test_missing: '测试缺失',
  rule_violation: '规范问题'
};

export const confidenceLevelLabels: Record<ConfidenceLevel, string> = {
  low: '低置信度',
  medium: '中置信度',
  high: '高置信度'
};

export const ruleTypeLabels: Record<RuleType, string> = {
  test: '测试要求',
  style: '规范要求',
  security: '安全规则',
  documentation: '文档同步',
  naming: '命名规范',
  module: '模块约束'
};

export const feedbackStatusLabels: Record<FeedbackStatus, string> = {
  none: '未反馈',
  useful: '有用',
  useless: '无用',
  false_positive: '误报',
  adopted: '已采纳',
  ignored: '暂不处理'
};
