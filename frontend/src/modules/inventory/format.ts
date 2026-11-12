import type { AttributeValue, FieldDef, ItemAction, ItemStatus } from './types'

export const ITEM_STATUS_LABEL: Record<ItemStatus, string> = {
  IN_STOCK: 'In stock',
  RESERVED: 'Reserved',
  ISSUED: 'Issued',
  DEPLOYED: 'Deployed',
  RETURNED: 'Returned',
  FAULTY: 'Faulty',
  IN_REPAIR: 'In repair',
  DISPOSED: 'Written off',
}

export const ITEM_STATUS_TONE: Record<ItemStatus, string> = {
  IN_STOCK: 'accent',
  RESERVED: 'warn',
  ISSUED: 'warn',
  DEPLOYED: 'ok',
  RETURNED: 'warn',
  FAULTY: 'bad',
  IN_REPAIR: 'bad',
  DISPOSED: 'muted',
}

export const ACTION_LABEL: Record<ItemAction, string> = {
  move: 'Move to another location',
  report_fault: 'Report a fault',
  send_for_repair: 'Send for repair',
  repaired: 'Back from repair',
  dispose: 'Write off',
}

export const MOVEMENT_LABEL: Record<string, string> = {
  RECEIVE: 'Received',
  UPDATE: 'Details changed',
  MOVE: 'Moved',
  REPORT_FAULT: 'Reported faulty',
  SEND_FOR_REPAIR: 'Sent for repair',
  REPAIRED: 'Back from repair',
  DISPOSE: 'Written off',
  RESERVE: 'Reserved',
  RELEASE: 'Released',
  ISSUE: 'Issued',
  DEPLOY: 'Deployed',
  RETURN: 'Returned',
  CHECK_IN: 'Checked and back in stock',
  TRANSFER_PROJECT: 'Transferred to another project',
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
