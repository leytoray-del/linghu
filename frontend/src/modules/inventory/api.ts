import { http } from '@/api/http'

import type {
  Category,
  Delivery,
  DeliveryInput,
  FieldDef,
  InventoryLookups,
  ItemAction,
  ItemDetail,
  ItemFilter,
  ItemModel,
  ItemPage,
  Movement,
  ProjectInventory,
  ProjectInventoryRow,
  SerialCheck,
  Supplier,
  AttributeValue,
} from './types'

function itemQuery(f: ItemFilter): URLSearchParams {
  const qs = new URLSearchParams()
  for (const key of ['project_id', 'category_id', 'model_id', 'warranty_within_days', 'page', 'page_size'] as const) {
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
  projects: () => http.get<ProjectInventoryRow[]>('/inventory/projects').then((r) => r.data),
  project: (id: number) => http.get<ProjectInventory>(`/inventory/projects/${id}`).then((r) => r.data),
  projectHistory: (id: number) => http.get<Movement[]>(`/inventory/projects/${id}/history`).then((r) => r.data),
  items: (f: ItemFilter) => http.get<ItemPage>(`/inventory/items?${itemQuery(f)}`).then((r) => r.data),
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
  act: (id: number, action: ItemAction, body: { version: number; location_id?: number | null; reason?: string | null }) =>
    http.post<ItemDetail>(`/inventory/items/${id}/actions/${action}`, body).then((r) => r.data),
  deliveries: (projectId?: number) =>
    http.get<Delivery[]>('/inventory/deliveries', { params: projectId ? { project_id: projectId } : {} }).then((r) => r.data),
  registerDelivery: (body: DeliveryInput) => http.post<Delivery>('/inventory/deliveries', body).then((r) => r.data),
  exportUrl: (projectId?: number) => `/api/v1/inventory/export.xlsx${projectId ? `?project_id=${projectId}` : ''}`,
  saveCategory: (body: CategoryInput, id?: number) =>
    (id ? http.put<Category>(`/inventory/categories/${id}`, body) : http.post<Category>('/inventory/categories', body)).then(
      (r) => r.data,
    ),
  saveModel: (body: Omit<ItemModel, 'id'>, id?: number) =>
    (id ? http.put<ItemModel>(`/inventory/models/${id}`, body) : http.post<ItemModel>('/inventory/models', body)).then(
      (r) => r.data,
    ),
  saveSupplier: (body: Omit<Supplier, 'id'>, id?: number) =>
    (id ? http.put<Supplier>(`/inventory/suppliers/${id}`, body) : http.post<Supplier>('/inventory/suppliers', body)).then(
      (r) => r.data,
    ),
}
