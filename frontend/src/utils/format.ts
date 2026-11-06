import dayjs from 'dayjs'

import type { RequestStatus, RequestType } from '@/types/api'

export const STATUS_LABEL: Record<RequestStatus, string> = {
  DRAFT: 'Draft',
  PENDING_TL_REVIEW: 'Pending TL review',
  PENDING_DIRECTOR_APPROVAL: 'Pending director approval',
  RETURNED: 'Returned for revision',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
  WITHDRAWN: 'Withdrawn',
  CANCELLED: 'Cancelled',
  CLOSED: 'Closed',
}

export type Tone = 'info' | 'accent' | 'warn' | 'ok' | 'bad' | 'muted'

export const STATUS_TONE: Record<RequestStatus, Tone> = {
  DRAFT: 'muted',
  PENDING_TL_REVIEW: 'accent',
  PENDING_DIRECTOR_APPROVAL: 'accent',
  RETURNED: 'warn',
  APPROVED: 'ok',
  REJECTED: 'bad',
  WITHDRAWN: 'muted',
  CANCELLED: 'muted',
  CLOSED: 'muted',
}

export const TYPE_LABEL: Record<RequestType, string> = {
  PROJECT: 'Project',
  PRESALES: 'Pre-sales',
  OTHER: 'Other',
}

export const STEP_LABEL: Record<string, string> = {
  TL_REVIEW: 'Team leader review',
  DIRECTOR_APPROVAL: 'Director approval',
  CHANGE_REVIEW: 'Change review',
}

export const EVENT_LABEL: Record<string, string> = {
  CREATE: 'Created a draft',
  SUBMIT: 'Submitted',
  RESUBMIT: 'Resubmitted',
  TL_APPROVE: 'Approved and proposed engineers',
  DIRECTOR_APPROVE: 'Approved',
  RETURN: 'Returned for revision',
  REJECT: 'Rejected',
  WITHDRAW: 'Withdrew the request',
  CANCEL: 'Cancelled the request',
  CLOSE: 'Closed',
  CHANGE_REQUEST: 'Asked for a change',
  CHANGE_APPROVE: 'Approved the change',
  CHANGE_REJECT: 'Rejected the change',
  CHANGE_WITHDRAW: 'Withdrew the change request',
  REASSIGN: 'Changed the reviewers',
}

export const PCT_OPTIONS = [100, 75, 50, 25]

/** Backend timestamps are naive UTC; dates are plain YYYY-MM-DD. */
export function parseUtc(value: string): dayjs.Dayjs {
  return dayjs(value.endsWith('Z') ? value : `${value}Z`)
}

export function fmtDate(value: string | null | undefined): string {
  return value ? dayjs(value).format('D MMM YYYY') : '—'
}

export function fmtDateTime(value: string | null | undefined): string {
  return value ? parseUtc(value).format('D MMM YYYY, HH:mm') : '—'
}

export function fmtRange(start: string | null, end: string | null): string {
  if (!start || !end) return '—'
  return `${fmtDate(start)} – ${fmtDate(end)}`
}

export function fmtHours(hours: number | null): string {
  if (hours === null) return '—'
  if (hours < 24) return `${hours.toFixed(1)} h`
  return `${(hours / 24).toFixed(1)} d`
}
