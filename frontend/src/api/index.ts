import { http } from './http'
import type {
  Action,
  AdminHoliday,
  AllocationInput,
  AdminSetting,
  AdminSupportType,
  AdminTeam,
  AdminUser,
  AllocationCandidate,
  Dashboard,
  EmailActionResult,
  EmailActionView,
  ListScope,
  LoadOut,
  Lookups,
  Me,
  NoticePreview,
  OutboxSummary,
  Page,
  ReportSummary,
  RequestDetail,
  RequestInput,
  RequestStatus,
  RequestSummary,
  Role,
  TaskInboxItem,
} from '@/types/api'

export const authApi = {
  login: (email: string, password: string) =>
    http.post<Me>('/auth/login', { email, password }).then((r) => r.data),
  logout: () => http.post('/auth/logout'),
  me: () => http.get<Me>('/auth/me').then((r) => r.data),
  changePassword: (current_password: string, new_password: string) =>
    http.post('/auth/change-password', { current_password, new_password }),
}

export interface ListParams {
  scope: ListScope
  status?: RequestStatus[]
  urgent?: boolean
  q?: string
  page?: number
  page_size?: number
}

function listQuery(params: ListParams): URLSearchParams {
  const qs = new URLSearchParams({ scope: params.scope })
  params.status?.forEach((s) => qs.append('status', s))
  if (params.urgent) qs.set('urgent', 'true')
  if (params.q) qs.set('q', params.q)
  if (params.page) qs.set('page', String(params.page))
  if (params.page_size) qs.set('page_size', String(params.page_size))
  return qs
}

export const requestApi = {
  list: (params: ListParams) =>
    http.get<Page<RequestSummary>>(`/requests?${listQuery(params)}`).then((r) => r.data),
  exportUrl: (params: ListParams) => `/api/v1/requests/export.xlsx?${listQuery(params)}`,
  get: (id: number) => http.get<RequestDetail>(`/requests/${id}`).then((r) => r.data),
  create: (body: RequestInput, submit: boolean) =>
    http.post<RequestDetail>(`/requests${submit ? '?submit=true' : ''}`, body).then((r) => r.data),
  update: (id: number, body: RequestInput, version: number) =>
    http.put<RequestDetail>(`/requests/${id}`, { ...body, version }).then((r) => r.data),
  remove: (id: number) => http.delete(`/requests/${id}`),
  submit: (id: number, version: number) =>
    http.post<RequestDetail>(`/requests/${id}/submit`, { version }).then((r) => r.data),
  decide: (id: number, action: Action, version: number, comment: string | null, allocations: AllocationInput[] = []) =>
    http
      .post<RequestDetail>(`/requests/${id}/decision`, { action, version, comment, allocations })
      .then((r) => r.data),
  requestChange: (
    id: number,
    body: { version: number; new_start: string; new_end: string; new_headcount: number; reason: string },
  ) => http.post<RequestDetail>(`/requests/${id}/changes`, body).then((r) => r.data),
  decideChange: (
    id: number,
    changeId: number,
    action: 'APPROVE' | 'REJECT',
    comment: string | null,
    allocations: AllocationInput[] = [],
  ) =>
    http
      .post<RequestDetail>(`/requests/${id}/changes/${changeId}/decision`, { action, comment, allocations })
      .then((r) => r.data),
  withdrawChange: (id: number, changeId: number) =>
    http.post<RequestDetail>(`/requests/${id}/changes/${changeId}/withdraw`).then((r) => r.data),
  withdraw: (id: number, version: number, comment: string | null) =>
    http.post<RequestDetail>(`/requests/${id}/withdraw`, { version, comment }).then((r) => r.data),
  cancel: (id: number, version: number, comment: string) =>
    http.post<RequestDetail>(`/requests/${id}/cancel`, { version, comment }).then((r) => r.data),
  close: (id: number, version: number) =>
    http.post<RequestDetail>(`/requests/${id}/close`, { version }).then((r) => r.data),
  candidates: (id: number, period?: { start: string; end: string }) =>
    http.get<AllocationCandidate[]>(`/requests/${id}/candidates`, { params: period }).then((r) => r.data),
  noticePreview: (planned_start: string) =>
    http.post<NoticePreview>('/requests/notice-preview', { planned_start }).then((r) => r.data),
  myTasks: () => http.get<TaskInboxItem[]>('/tasks/mine').then((r) => r.data),
}

/** Public endpoints behind the links in approver emails; the token authenticates the approver. */
export const emailActionApi = {
  view: (token: string) => http.get<EmailActionView>(`/email-actions/${encodeURIComponent(token)}`).then((r) => r.data),
  act: (token: string, body: { action: Action; comment: string | null; allocations: AllocationInput[] }) =>
    http.post<EmailActionResult>(`/email-actions/${encodeURIComponent(token)}`, body).then((r) => r.data),
}

export const referenceApi = {
  lookups: () => http.get<Lookups>('/lookups').then((r) => r.data),
  dashboard: () => http.get<Dashboard>('/dashboard').then((r) => r.data),
  report: (year?: number) =>
    http.get<ReportSummary>('/reports/summary', { params: { year } }).then((r) => r.data),
  load: (params: { start?: string; end?: string; team_id?: number }) =>
    http.get<LoadOut>('/resources/load', { params }).then((r) => r.data),
}

export interface UserForm {
  email?: string
  display_name: string
  job_title: string | null
  team_id: number | null
  skills: string | null
  roles: Role[]
  is_active?: boolean
}

export const adminApi = {
  users: () => http.get<AdminUser[]>('/admin/users').then((r) => r.data),
  createUser: (body: UserForm) =>
    http
      .post<{ user: AdminUser; temporary_password: string }>('/admin/users', body)
      .then((r) => r.data),
  updateUser: (id: number, body: UserForm) =>
    http.put<AdminUser>(`/admin/users/${id}`, body).then((r) => r.data),
  resetPassword: (id: number) =>
    http
      .post<{ user: AdminUser; temporary_password: string }>(`/admin/users/${id}/reset-password`)
      .then((r) => r.data),
  teams: () => http.get<AdminTeam[]>('/admin/teams').then((r) => r.data),
  setApprovers: (teamId: number, approver_ids: number[]) =>
    http.put<AdminTeam>(`/admin/teams/${teamId}/approvers`, { approver_ids }).then((r) => r.data),
  supportTypes: () => http.get<AdminSupportType[]>('/admin/support-types').then((r) => r.data),
  saveSupportType: (body: Omit<AdminSupportType, 'id'>, id?: number) =>
    (id
      ? http.put<AdminSupportType>(`/admin/support-types/${id}`, body)
      : http.post<AdminSupportType>('/admin/support-types', body)
    ).then((r) => r.data),
  holidays: (year?: number) =>
    http.get<AdminHoliday[]>('/admin/holidays', { params: { year } }).then((r) => r.data),
  addHoliday: (holiday_date: string, name: string) =>
    http.post<AdminHoliday>('/admin/holidays', { holiday_date, name }).then((r) => r.data),
  deleteHoliday: (id: number) => http.delete(`/admin/holidays/${id}`),
  settings: () => http.get<AdminSetting[]>('/admin/settings').then((r) => r.data),
  setSetting: (key: string, value: string) =>
    http.put<AdminSetting[]>(`/admin/settings/${key}`, { value }).then((r) => r.data),
  outbox: (status_filter?: string) =>
    http.get<OutboxSummary>('/admin/outbox', { params: { status_filter } }).then((r) => r.data),
  retryEmail: (id: number) => http.post(`/admin/outbox/${id}/retry`),
  sendTestEmail: (to: string) =>
    http
      .post<{ status: 'SENT' | 'LOGGED' | 'FAILED'; backend: string; delivered_to: string[]; error: string | null }>(
        '/admin/email-test',
        { to },
      )
      .then((r) => r.data),
}
