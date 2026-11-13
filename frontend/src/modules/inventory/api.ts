import { http } from '@/api/http'

import type { Location } from '@/types/api'

import type {
  AttributeValue,
  Category,
  Delivery,
  DeliveryInput,
  FieldDef,
  InventoryLookups,
  InventorySummary,
  ItemDetail,
  ItemFilter,
  ItemModel,
  ItemPage,
  SerialCheck,
  Withdrawal,
  WithdrawalDetail,
  WithdrawalInput,
  WithdrawalStatus,
} from './types'

function itemQuery(f: ItemFilter): URLSearchParams {
  const qs = new URLSearchParams()
  for (const key of ['project_id', 'category_id', 'model_id', 'location_id', 'warranty_within_days', 'page', 'page_size'] as const) {
    const v = f[key]
    if (v !== undefined && v !== null) qs.set(key, String(v))
  }
  f.status?.forEach((s) => qs.append('status', s))
  if (f.q) qs.set('q', f.q)
  return qs
}

export interface CategoryInput {
  code: string
  name: string
  fields: FieldDef[]
  warranty_required: boolean
  is_active: boolean
}

export const inventoryApi = {
  lookups: () => http.get<InventoryLookups>('/inventory/lookups').then((r) => r.data),
  items: (f: ItemFilter) => http.get<ItemPage>(`/inventory/items?${itemQuery(f)}`).then((r) => r.data),
  summary: (f: ItemFilter) => {
    const qs = itemQuery({ ...f, status: undefined, page: undefined, page_size: undefined, warranty_within_days: undefined })
    return http.get<InventorySummary>(`/inventory/summary?${qs}`).then((r) => r.data)
  },
  item: (id: number) => http.get<ItemDetail>(`/inventory/items/${id}`).then((r) => r.data),
  checkSerial: (serial: string) =>
    http.get<SerialCheck>('/inventory/items/check-serial', { params: { serial } }).then((r) => r.data),
  updateItem: (
    id: number,
    body: {
      version: number
      warranty_start: string | null
      warranty_end: string | null
      attributes: Record<string, AttributeValue>
      remarks: string | null
    },
  ) => http.put<ItemDetail>(`/inventory/items/${id}`, body).then((r) => r.data),
  deleteItem: (id: number, version: number, reason: string) =>
    http.post<ItemDetail>(`/inventory/items/${id}/delete`, { version, reason }).then((r) => r.data),
  returnItem: (id: number, version: number, locationId: number, reason: string | null) =>
    http.post<ItemDetail>(`/inventory/items/${id}/return`, { version, location_id: locationId, reason }).then((r) => r.data),
  registerDevices: (body: DeliveryInput) => http.post<Delivery>('/inventory/deliveries', body).then((r) => r.data),
  exportUrl: (projectId?: number) => `/api/v1/inventory/export.xlsx${projectId ? `?project_id=${projectId}` : ''}`,
  withdrawals: (scope: 'mine' | 'waiting' | 'all', status?: WithdrawalStatus[]) => {
    const qs = new URLSearchParams({ scope })
    status?.forEach((s) => qs.append('status', s))
    return http.get<Withdrawal[]>(`/inventory/withdrawals?${qs}`).then((r) => r.data)
  },
  withdrawal: (id: number) => http.get<WithdrawalDetail>(`/inventory/withdrawals/${id}`).then((r) => r.data),
  createWithdrawal: (body: WithdrawalInput) =>
    http.post<WithdrawalDetail>('/inventory/withdrawals', body).then((r) => r.data),
  reviseWithdrawal: (id: number, body: WithdrawalInput & { version: number }) =>
    http.put<WithdrawalDetail>(`/inventory/withdrawals/${id}`, body).then((r) => r.data),
  decideWithdrawal: (id: number, version: number, approve: boolean, comment: string | null) =>
    http
      .post<WithdrawalDetail>(`/inventory/withdrawals/${id}/decision`, { version, approve, comment })
      .then((r) => r.data),
  withdrawWithdrawal: (id: number, version: number, comment: string | null) =>
    http.post<WithdrawalDetail>(`/inventory/withdrawals/${id}/withdraw`, { version, comment }).then((r) => r.data),
  addSite: (name: string) => http.post<Location>('/inventory/sites', { name }).then((r) => r.data),
  saveCategory: (body: CategoryInput, id?: number) =>
    (id ? http.put<Category>(`/inventory/categories/${id}`, body) : http.post<Category>('/inventory/categories', body)).then(
      (r) => r.data,
    ),
  saveModel: (body: Omit<ItemModel, 'id'>, id?: number) =>
    (id ? http.put<ItemModel>(`/inventory/models/${id}`, body) : http.post<ItemModel>('/inventory/models', body)).then(
      (r) => r.data,
    ),
}
