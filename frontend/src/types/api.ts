// Types mirroring the backend response schemas (backend/src/erf/schemas).

export type Role =
  | 'REQUESTER'
  | 'TEAM_LEADER'
  | 'DIRECTOR'
  | 'ENGINEER'
  | 'ADMIN'
  | 'VIEWER'
  | 'INVENTORY_CLERK'
  | 'OPS_MANAGER'
export type RequestType = 'PROJECT' | 'PRESALES' | 'OTHER'
export type Priority = 'NORMAL' | 'URGENT'
export type RequestStatus =
  | 'DRAFT'
  | 'PENDING_TL_REVIEW'
  | 'PENDING_DIRECTOR_APPROVAL'
  | 'RETURNED'
  | 'APPROVED'
  | 'REJECTED'
  | 'WITHDRAWN'
  | 'CANCELLED'
  | 'CLOSED'
export type Action = 'SUBMIT' | 'APPROVE' | 'RETURN' | 'REJECT' | 'WITHDRAW' | 'CANCEL' | 'CLOSE'
export type ListScope = 'mine' | 'team' | 'all' | 'assigned'

export interface UserRef {
  id: number
  display_name: string
  email: string
  job_title: string | null
}

export interface TeamBrief {
  id: number
  code: string
  name: string
}

export interface Me {
  id: number
  email: string
  display_name: string
  job_title: string | null
  team: TeamBrief | null
  roles: Role[]
  led_team_ids: number[]
  scopes: ListScope[]
  /** Permissions granted by the user's roles, such as inventory.view. Pages check these, not role names. */
  permissions: string[]
  must_change_password: boolean
  pending_task_count: number
  /** Withdrawal requests waiting for this person's approval. */
  withdrawal_task_count: number
}

export interface SupportTypeBrief {
  id: number
  code: string
  name: string
  team_id: number
}

export interface EngineerBrief {
  id: number
  display_name: string
  skills: string | null
}

export interface TeamLookup extends TeamBrief {
  engineers: EngineerBrief[]
  approvers: string[]
}

export interface Lookups {
  support_types: SupportTypeBrief[]
  teams: TeamLookup[]
  directors: string[]
  min_notice_working_days: number
  today: string
}

export interface RequestSummary {
  id: number
  request_no: string | null
  display_no: string
  status: RequestStatus
  request_type: RequestType | null
  is_urgent: boolean
  notice_working_days: number | null
  project_name: string | null
  client_name: string | null
  support_type: SupportTypeBrief | null
  team: TeamBrief | null
  headcount: number | null
  planned_start: string | null
  planned_end: string | null
  requester: UserRef
  current_handlers: UserRef[]
  submitted_at: string | null
  updated_at: string
  version: number
}

export interface AllocationOut {
  id: number
  engineer: UserRef
  start_date: string
  end_date: string
  allocation_pct: number
  status: 'PROPOSED' | 'CONFIRMED' | 'RELEASED'
}

export type ChangeStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'WITHDRAWN'

export interface ChangeOut {
  id: number
  status: ChangeStatus
  summary: string
  reason: string
  old_start: string
  old_end: string
  old_headcount: number | null
  new_start: string
  new_end: string
  new_headcount: number | null
  requested_by: UserRef
  decided_by: UserRef | null
  decision_comment: string | null
  decided_at: string | null
  created_at: string
}

export type Step = 'TL_REVIEW' | 'DIRECTOR_APPROVAL' | 'CHANGE_REVIEW'

export interface AllocationInput {
  engineer_id: number
  allocation_pct: number
}

export interface TaskOut {
  id: number
  round: number
  step: Step
  assignee: UserRef
  status: 'PENDING' | 'APPROVED' | 'RETURNED' | 'REJECTED' | 'CLOSED'
  decision_comment: string | null
  due_at: string | null
  acted_at: string | null
  created_at: string
}

export interface EventOut {
  id: number
  action: string
  actor: UserRef | null
  from_status: RequestStatus | null
  to_status: RequestStatus | null
  comment: string | null
  payload: Record<string, unknown> | null
  created_at: string
}

export interface RequestDetail extends RequestSummary {
  priority_declared: Priority
  urgency_reason: 'SHORT_NOTICE' | 'DECLARED' | null
  wbs_code: string | null
  preferred_engineers: UserRef[]
  preferred_engineers_note: string | null
  man_days: number | null
  scope_description: string | null
  task_schedule: string | null
  urgent_justification: string | null
  round: number
  first_submitted_at: string | null
  decided_at: string | null
  allocations: AllocationOut[]
  tasks: TaskOut[]
  events: EventOut[]
  available_actions: Action[]
  can_edit: boolean
  can_delete: boolean
  changes: ChangeOut[]
  can_request_change: boolean
  change_awaiting_me: number | null
}

export interface RequestInput {
  request_type: RequestType | null
  priority_declared: Priority
  project_name: string | null
  wbs_code: string | null
  client_name: string | null
  support_type_id: number | null
  headcount: number | null
  preferred_engineer_ids: number[]
  preferred_engineers_note: string | null
  man_days: number | null
  planned_start: string | null
  planned_end: string | null
  scope_description: string | null
  task_schedule: string | null
  urgent_justification: string | null
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface NoticePreview {
  submitted_on: string
  planned_start: string
  notice_working_days: number
  min_notice_working_days: number
  is_short_notice: boolean
  holidays: { holiday_date: string; name: string }[]
}

export interface CandidateAssignment {
  request_id: number
  display_no: string
  project_name: string | null
  start_date: string
  end_date: string
  allocation_pct: number
  status: string
}

export interface AllocationCandidate {
  engineer: UserRef
  skills: string | null
  is_preferred: boolean
  overlapping: CandidateAssignment[]
  peak_pct: number
}

export interface TaskInboxItem {
  task_id: number
  step: Step
  due_at: string | null
  is_overdue: boolean
  request: RequestSummary
  change_summary: string | null
}

export interface Dashboard {
  my_open: number
  my_returned: number
  my_approved: number
  my_drafts: number
  my_total: number
  pending_tasks: number
  pending_urgent: number
  overdue_tasks: number
  team_requests_open: number
  assigned_active: number
}

export interface LoadAssignment {
  request_id: number
  display_no: string
  project_name: string | null
  client_name: string | null
  start_date: string
  end_date: string
  allocation_pct: number
  status: string
}

export interface EngineerLoad {
  engineer: UserRef
  team_id: number | null
  team_name: string | null
  skills: string | null
  assignments: LoadAssignment[]
}

export interface LoadOut {
  start: string
  end: string
  engineers: EngineerLoad[]
}

export interface NamedCount {
  name: string
  count: number
}

export interface ReportSummary {
  year: number
  total: number
  urgent: number
  urgent_share: number
  approved: number
  approved_man_days: number
  median_tl_hours: number | null
  median_director_hours: number | null
  by_month: { month: string; normal: number; urgent: number }[]
  by_status: NamedCount[]
  by_support_type: NamedCount[]
  by_team: NamedCount[]
}

// Administration
export interface AdminUser {
  id: number
  email: string
  display_name: string
  job_title: string | null
  team: TeamBrief | null
  skills: string | null
  roles: Role[]
  is_active: boolean
  must_change_password: boolean
  last_login_at: string | null
}

export interface AdminTeam extends TeamBrief {
  is_active: boolean
  approvers: UserRef[]
  reassigned_requests: number
}

export interface AdminSupportType {
  id: number
  code: string
  name: string
  team_id: number
  sort_order: number
  is_active: boolean
}

export interface AdminHoliday {
  id: number
  holiday_date: string
  name: string
}

export interface AdminSetting {
  key: string
  value: string
  description: string
}

export interface OutboxItem {
  id: number
  event_type: string
  request_id: number | null
  to_addresses: string[]
  cc_addresses: string[]
  subject: string
  status: 'PENDING' | 'SENT' | 'FAILED' | 'SKIPPED'
  attempts: number
  last_error: string | null
  created_at: string
  sent_at: string | null
}

export interface OutboxSummary {
  counts: Record<string, number>
  items: OutboxItem[]
  backend: string
}

export interface EmailActionView {
  step: Step
  assignee: UserRef
  expires_at: string
  actions: Action[]
  request: RequestDetail
  change: ChangeOut | null
  candidates: AllocationCandidate[]
  preselected: AllocationInput[]
}

export interface EmailActionResult {
  message: string
  request_id: number
  display_no: string
  status: RequestStatus
}

export interface UserImportRow {
  row: number
  email: string
  name: string
  outcome: 'create' | 'update' | 'unchanged' | 'error'
  changes: string[]
  error: string | null
}

export interface UserImportResult {
  applied: boolean
  created: number
  updated: number
  unchanged: number
  errors: number
  rows: UserImportRow[]
}

// Shared organisation records
export type LocationKind = 'STORE' | 'SITE' | 'REPAIR' | 'OTHER'

export interface Project {
  id: number
  code: string
  name: string
  client_name: string | null
  pm: UserRef | null
  remarks: string | null
  is_active: boolean
}

export interface ProjectInput {
  code: string
  name: string
  client_name: string | null
  pm_user_id: number | null
  remarks: string | null
  is_active: boolean
}

export interface Location {
  id: number
  name: string
  kind: LocationKind
  is_active: boolean
}
