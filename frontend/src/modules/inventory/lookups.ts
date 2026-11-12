import { ref } from 'vue'

import { inventoryApi } from './api'
import type { Category, FieldDef, InventoryLookups } from './types'

/** Categories, models, suppliers, locations and projects, loaded once and shared by the inventory pages. */
const data = ref<InventoryLookups | null>(null)
let pending: Promise<InventoryLookups> | null = null

export function useInventoryLookups() {
  async function load(force = false): Promise<InventoryLookups> {
    if (data.value && !force) return data.value
    if (!pending || force) {
      pending = inventoryApi.lookups().then((d) => (data.value = d))
      pending.finally(() => (pending = null))
    }
    return pending
  }
  function category(id: number | null | undefined): Category | undefined {
    return data.value?.categories.find((c) => c.id === id)
  }
  function categoryOfModel(modelId: number | null | undefined): Category | undefined {
    const m = data.value?.models.find((x) => x.id === modelId)
    return m ? category(m.category_id) : undefined
  }
  function listFields(categoryId: number | null | undefined): FieldDef[] {
    return (category(categoryId)?.fields ?? []).filter((f) => f.show_in_list && !f.retired)
  }
  return { data, load, category, categoryOfModel, listFields }
}
