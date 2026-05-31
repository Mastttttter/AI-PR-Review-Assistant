export type ReviewTaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'deleted';
export type RiskLevel = 'low' | 'medium' | 'high';
export type IssueSeverity = 'low' | 'medium' | 'high';
export type IssueType = 'logic' | 'exception' | 'security' | 'performance' | 'maintainability' | 'test_missing' | 'rule_violation';
export type ConfidenceLevel = 'low' | 'medium' | 'high';
export type RuleType = 'test' | 'style' | 'security' | 'documentation' | 'naming' | 'module';
export type FeedbackStatus = 'none' | 'useful' | 'useless' | 'false_positive' | 'adopted' | 'ignored';

export interface ReviewTask {
  id: string;
  prTitle: string;
  prDescription?: string | null;
  projectName?: string | null;
  targetBranch?: string | null;
  developerName?: string | null;
  prUrl?: string | null;
  status: ReviewTaskStatus;
  riskLevel?: RiskLevel | null;
  issueCount: number;
  createdBy?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface CreateReviewTaskRequest {
  prTitle: string;
  prDescription?: string;
  projectName?: string;
  targetBranch?: string;
  developerName?: string;
  prUrl?: string;
  diffContent: string;
}

export interface CreateReviewTaskResponse {
  taskId: string;
  status: ReviewTaskStatus;
}

export interface ReviewTaskListQuery {
  projectName?: string;
  riskLevel?: RiskLevel;
  status?: ReviewTaskStatus;
  createdFrom?: string;
  createdTo?: string;
}

export interface ReviewSummary {
  purpose: string;
  changedModules: string[];
  keyFiles: string[];
  businessImpact: string;
  testOrSecurityNotes: string;
}

export interface ReviewRisk {
  level: RiskLevel;
  reasons: string[];
}

export interface IssueLocation {
  filePath?: string | null;
  lineHint?: string | null;
  codeSnippet?: string | null;
}

export interface ReviewIssue {
  id: string;
  taskId: string;
  reportId: string;
  title: string;
  type: IssueType;
  severity: IssueSeverity;
  description: string;
  location: IssueLocation;
  suggestion: string;
  confidence: ConfidenceLevel;
  matchedRuleIds: string[];
  feedbackStatus: FeedbackStatus;
  createdAt: string;
}

export interface IssueStats {
  total: number;
  high: number;
  medium: number;
  low: number;
  ruleHits: number;
}

export interface ReviewReport {
  id: string;
  task: ReviewTask;
  summary: ReviewSummary;
  risk: ReviewRisk;
  issueStats: IssueStats;
  issues: ReviewIssue[];
  createdAt: string;
}

export interface ReviewRule {
  id: string;
  name: string;
  description: string;
  type: RuleType;
  severity: IssueSeverity;
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface UpsertReviewRuleRequest {
  name: string;
  description: string;
  type: RuleType;
  severity: IssueSeverity;
  enabled: boolean;
}

export interface FeedbackRequest {
  feedbackStatus: Exclude<FeedbackStatus, 'none'>;
  comment?: string;
}

export interface FeedbackResponse {
  issueId: string;
  taskId: string;
  feedbackStatus: FeedbackStatus;
  comment?: string | null;
  updatedAt: string;
}

export interface DashboardResponse {
  totalTasks: number;
  recentTasks: number;
  totalIssues: number;
  riskDistribution: Record<string, number>;
  usefulRate: number;
  falsePositiveRate: number;
  adoptionRate: number;
}

export interface ProviderConfig {
  baseUri: string;
  apiKey: string;
  model: string;
}

export interface SettingsResponse {
  openai: ProviderConfig;
  anthropic: ProviderConfig;
  activeProvider: string;
  mockEnabled: boolean;
  systemPrompt: string;
}

export interface TestConnectionRequest {
  provider: string;
  baseUri: string;
  apiKey?: string;
  model: string;
}

export interface TestConnectionResponse {
  success: boolean;
  message: string;
}

export interface FetchPrRequest {
  url: string;
}

export interface FetchPrResponse {
  title: string;
  description: string;
  diffContent: string;
  projectName: string;
  targetBranch: string;
  developerName: string;
}

export interface DispatcherFetchRequest {
  url: string;
}

export interface DispatcherFetchResponse {
  apiKey: string;
  baseUri: string;
  model: string;
  openaiModel: string;
  anthropicModel: string;
  expiresIn: number;
}
