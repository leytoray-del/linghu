import type { Location, Page, Project, UserRef } from '@/types/api'

export type ItemStatus = 'IN_STOCK' | 'REQUESTED' | 'DEPLOYED'
export type WithdrawalStatus = 'PENDING_PM' | 'PENDING_OM' | 'APPROVED' | 'RETURNED' | 'WITHDRAWN'
export type FieldType = 'text' | 'number' | 'date' | 'choice' | 'boolean'
export type AttributeValue = string | number | boolean | null

export interface FieldDef {
  key: string
  label: string
  type: FieldType
  choices: string[]
  required: boolean
  show_in_list: boolean
  retired: boolean
}

export interface Category {
  id: number
  code: string
  name: string
  fields: FieldDef[]
  warranty_required: boolean
  is_active: boolean
}

export interface ItemModel {
  id: number
  category_id: number
  model_no: string
  name: string | null
  manufacturer: string | null
  serial_pattern: string | null
  is_active: boolean
}

export interface Supplier {
  id: number
  name: string
  is_active: boolean
}

export interface InventoryLookups {
  categories: Category[]
  models: ItemModel[]
  suppliers: Supplier[]
  locations: Location[]
  projects: Project[]
}

export interface StatusCounts {
  in_stock: number
  requested: number
  deployed: number
  total: number
}

export interface InventorySummary {
  counts: StatusCounts
  warranty_ending: number
}

export interface Item {
  id: number
  serial_no: string
  category_id: number
  category_name: string
  model_id: number
  model_no: string
  project: Project
  location: Location
  status: ItemStatus
  warranty_start: string | null
  warranty_end: string | null
  holder: UserRef | null
  delivery_no: string | null
  attributes: Record<string, AttributeValue>
  remarks: string | null
  version: number
}

export interface Movement {
  id: number
  kind: string
  from_status: string | null
  to_status: string | null
  from_location: string | null
  to_location: string | null
  withdrawal_id: number | null
  withdrawal_no: string | null
  changes: Record<string, { from: AttributeValue; to: AttributeValue }> | null
  reason: string | null
  actor: UserRef
  occurred_at: string
}

export interface ItemDetail extends Item {
  history: Movement[]
  open_withdrawal: { id: number; request_no: string; status: WithdrawalStatus } | null
  deleted_at: string | null
  deleted_by: UserRef | null
  delete_reason: string | null
}

export interface DeliveryItemInput {
  serial_no: string
  model_id: number
  warranty_start: string | null
  warranty_end: string | null
  attributes: Record<string, AttributeValue>
  remarks?: string | null
}

export interface DeliveryInput {
  project_id: number
  supplier_id: number | null
  delivery_order_no: string | null
  received_on: string
  location_id: number
  remarks: string | null
  items: DeliveryItemInput[]
}

export interface Delivery {
  id: number
  delivery_no: string
  project: Project
  supplier: Supplier | null
  delivery_order_no: string | null
  received_on: string
  received_by: UserRef
  location: Location
  item_count: number
  remarks: string | null
  created_at: string
}

export interface SerialCheck {
  serial_no: string
  exists: boolean
  message: string | null
  item_id: number | null
}

export interface ItemFilter {
  project_id?: number
  category_id?: number
  model_id?: number
  location_id?: number
  status?: ItemStatus[]
  q?: string
  warranty_within_days?: number
  page?: number
  page_size?: number
}

export type ItemPage = Page<Item>

export interface WithdrawalTask {
  round: number
  step: 'PM' | 'OM'
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'SKIPPED' | 'CLOSED'
  approvers: UserRef[]
  decided_by: UserRef | null
  comment: string | null
  decided_at: string | null
}

export interface Withdrawal {
  id: number
  request_no: string
  project: Project
  requester: UserRef
  to_location: Location
  reason: string
  status: WithdrawalStatus
  item_count: number
  submitted_at: string
  completed_at: string | null
  waiting_for: UserRef[]
  version: number
}

export interface WithdrawalDetail extends Withdrawal {
  items: Item[]
  tasks: WithdrawalTask[]
  events: { action: string; actor: UserRef; comment: string | null; occurred_at: string }[]
  can_decide: boolean
  can_revise: boolean
  can_withdraw: boolean
}

export interface WithdrawalInput {
  project_id: number
  item_ids: number[]
  to_location_id: number
  reason: string
}
