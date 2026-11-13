import type { AttributeValue, FieldDef, ItemStatus, WithdrawalStatus } from './types'

export const ITEM_STATUS_LABEL: Record<ItemStatus, string> = {
  IN_STOCK: 'In stock',
  REQUESTED: 'Requested',
  DEPLOYED: 'Deployed',
}

export const ITEM_STATUS_TONE: Record<ItemStatus, string> = {
  IN_STOCK: 'accent',
  REQUESTED: 'warn',
  DEPLOYED: 'ok',
}

export const MOVEMENT_LABEL: Record<string, string> = {
  RECEIVE: 'Registered',
  UPDATE: 'Details changed',
  REQUEST: 'Requested for withdrawal',
  RELEASE: 'Back in stock (request not approved)',
  DEPLOY: 'Deployed',
  RETURN: 'Returned to stock',
  DELETE: 'Deleted',
}

export const WITHDRAWAL_STATUS_LABEL: Record<WithdrawalStatus, string> = {
  PENDING_PM: 'Waiting for PM',
  PENDING_OM: 'Waiting for OM',
  APPROVED: 'Approved',
  RETURNED: 'Rejected · can resubmit',
  WITHDRAWN: 'Withdrawn',
}

export const WITHDRAWAL_STATUS_TONE: Record<WithdrawalStatus, string> = {
  PENDING_PM: 'accent',
  PENDING_OM: 'accent',
  APPROVED: 'ok',
  RETURNED: 'warn',
  WITHDRAWN: 'muted',
}

export const WITHDRAWAL_EVENT_LABEL: Record<string, string> = {
  SUBMIT: 'Submitted',
  RESUBMIT: 'Revised and resubmitted',
  APPROVE_PM: 'Approved by the PM',
  REJECT_PM: 'Rejected by the PM',
  APPROVE_OM: 'Approved by the operations manager',
  REJECT_OM: 'Rejected by the operations manager',
  WITHDRAW: 'Withdrawn by the requester',
}

export const LOCATION_KIND_LABEL: Record<string, string> = {
  STORE: 'Store',
  SITE: 'Site',
  REPAIR: 'Repair centre',
  OTHER: 'Other',
}

export const FIELD_TYPE_LABEL: Record<string, string> = {
  text: 'Text',
  number: 'Number',
  date: 'Date',
  choice: 'Choice',
  boolean: 'Yes or no',
}

/** How a category field's value is shown in lists and on the item page. */
export function showValue(field: FieldDef | undefined, value: AttributeValue | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (field?.type === 'date' && typeof value === 'string') {
    const d = new Date(`${value}T00:00:00`)
    return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
  }
  return String(value)
}
