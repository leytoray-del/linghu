<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { showError } from '@/utils/feedback'
import { fmtDate, fmtDateTime } from '@/utils/format'

import { inventoryApi } from '../api'
import ItemStatusTag from '../components/ItemStatusTag.vue'
import { ITEM_STATUS_LABEL, MOVEMENT_LABEL, showValue } from '../format'
import { useInventoryLookups } from '../lookups'
import type { Delivery, Item, ItemStatus, Movement, ProjectInventory } from '../types'

const route = useRoute()
const auth = useAuthStore()
const lk = useInventoryLookups()

const projectId = computed(() => Number(route.params.id))
const data = ref<ProjectInventory | null>(null)
const tab = ref<'items' | 'deliveries' | 'history'>('items')
const categoryId = ref<number | null>(null)
const status = ref<ItemStatus | ''>('')
const query = ref('')
const items = ref<Item[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const loadingItems = ref(false)
const deliveries = ref<Delivery[] | null>(null)
const history = ref<Movement[] | null>(null)

const STATUS_COLUMNS: { key: keyof ProjectInventory['totals']; label: string }[] = [
  { key: 'in_stock', label: 'In stock' },
  { key: 'reserved', label: 'Reserved' },
  { key: 'issued', label: 'Issued' },
  { key: 'deployed', label: 'Deployed' },
  { key: 'returned', label: 'Returned' },
  { key: 'faulty', label: 'Faulty' },
  { key: 'in_repair', label: 'In repair' },
]
const listFields = computed(() => (categoryId.value ? lk.listFields(categoryId.value) : []))
const categoryFields = computed(() => lk.category(categoryId.value)?.fields ?? [])

async function loadSummary(): Promise<void> {
  try {
    await lk.load()
    data.value = await inventoryApi.project(projectId.value)
    if (categoryId.value === null && data.value.by_category.length) {
      categoryId.value = data.value.by_category.find((c) => c.category_name === 'FR reader')?.category_id ?? data.value.by_category[0]!.category_id
    }
  } catch (e) {
    showError(e)
  }
}

async function loadItems(): Promise<void> {
  loadingItems.value = true
  try {
    const result = await inventoryApi.items({
      project_id: projectId.value,
      category_id: categoryId.value ?? undefined,
      status: status.value ? [status.value] : undefined,
      q: query.value.trim() || undefined,
      page: page.value,
      page_size: pageSize,
    })
    items.value = result.items
    total.value = result.total
  } catch (e) {
    showError(e)
  } finally {
    loadingItems.value = false
  }
}

let searchTimer: number | undefined
watch(query, () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    page.value = 1
    loadItems()
  }, 300)
})
watch([categoryId, status], () => {
  page.value = 1
  loadItems()
})
watch(page, loadItems)
watch(tab, async (t) => {
  try {
    if (t === 'deliveries' && deliveries.value === null) deliveries.value = await inventoryApi.deliveries(projectId.value)
    if (t === 'history' && history.value === null) history.value = await inventoryApi.projectHistory(projectId.value)
  } catch (e) {
    showError(e)
  }
})
watch(
  projectId,
  async () => {
    categoryId.value = null
    deliveries.value = null
    history.value = null
    tab.value = 'items'
    await loadSummary()
    await loadItems()
  },
  { immediate: true },
)

function describe(m: Movement): string {
  const parts: string[] = []
  if (m.to_location && m.to_location !== m.from_location) parts.push(m.from_location ? `${m.from_location} → ${m.to_location}` : m.to_location)
  if (m.delivery_no) parts.push(m.delivery_no)
  if (m.changes) parts.push(Object.keys(m.changes).join(', '))
  if (m.reason) parts.push(m.reason)
  return parts.join(' · ')
}
</script>

<template>
  <div class="page">
    <div v-if="data" class="page-head">
      <div>
        <RouterLink to="/inventory" class="back">Project inventory</RouterLink>
        <h1>{{ data.project.name }}</h1>
        <p class="sub">
          <span class="mono">{{ data.project.code }}</span>
          <template v-if="data.project.client_name"> · Client {{ data.project.client_name }}</template>
          · PM {{ data.project.pm?.display_name ?? 'not set' }}
          <el-tag v-if="!data.project.is_active" size="small" type="info">Closed</el-tag>
        </p>
      </div>
      <div class="actions">
        <el-button tag="a" :href="inventoryApi.exportUrl(projectId)">Export to Excel</el-button>
        <el-button
          v-if="auth.can('inventory.register') && data.project.is_active"
          type="primary"
          @click="$router.push({ path: '/inventory/deliveries/new', query: { project: projectId } })"
        >
          Register device
        </el-button>
      </div>
    </div>

    <section v-if="data" class="panel">
      <div class="panel-head">
        <h2>Equipment by category</h2>
        <span v-if="data.warranty_ending" class="warn small">{{ data.warranty_ending }} warranties end within 60 days</span>
      </div>
      <div class="table-scroll">
        <table class="summary">
          <thead>
            <tr>
              <th>Category</th>
              <th v-for="c in STATUS_COLUMNS" :key="c.key">{{ c.label }}</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="c in data.by_category"
              :key="c.category_id"
              :class="{ selected: c.category_id === categoryId }"
              @click="categoryId = c.category_id; tab = 'items'"
            >
              <td><b>{{ c.category_name }}</b></td>
              <td v-for="col in STATUS_COLUMNS" :key="col.key" class="num">{{ c.counts[col.key] || '·' }}</td>
              <td class="num"><b>{{ c.counts.total }}</b></td>
            </tr>
            <tr v-if="data.by_category.length > 1" class="total">
              <td><b>All categories</b></td>
              <td v-for="col in STATUS_COLUMNS" :key="col.key" class="num"><b>{{ data.totals[col.key] || '·' }}</b></td>
              <td class="num"><b>{{ data.totals.total }}</b></td>
            </tr>
            <tr v-if="!data.by_category.length">
              <td :colspan="STATUS_COLUMNS.length + 2" class="muted empty">No equipment is registered for this project yet.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="data" class="panel">
      <el-tabs v-model="tab">
        <el-tab-pane label="Items" name="items">
          <div class="filters">
            <div class="chips" role="group" aria-label="Category">
              <button
                v-for="c in data.by_category"
                :key="c.category_id"
                type="button"
                :aria-pressed="c.category_id === categoryId"
                @click="categoryId = c.category_id"
              >
                {{ c.category_name }} ({{ c.counts.total }})
              </button>
              <button type="button" :aria-pressed="categoryId === null" @click="categoryId = null">All</button>
            </div>
            <div class="filter-row">
              <el-input v-model="query" placeholder="Search serial number or any field" clearable class="search" />
              <el-select v-model="status" placeholder="Any status" clearable class="status-select">
                <el-option v-for="(label, key) in ITEM_STATUS_LABEL" :key="key" :label="label" :value="key" />
              </el-select>
            </div>
          </div>
          <el-table
            v-loading="loadingItems"
            :data="items"
            empty-text="No items match."
            class="clickable"
            @row-click="(i: Item) => $router.push(`/inventory/items/${i.id}`)"
          >
            <el-table-column label="Serial no." min-width="140">
              <template #default="{ row }">
                <RouterLink :to="`/inventory/items/${row.id}`" class="mono" @click.stop>{{ row.serial_no }}</RouterLink>
              </template>
            </el-table-column>
            <el-table-column v-if="!categoryId" label="Category" min-width="110" prop="category_name" />
            <el-table-column label="Model" min-width="100" prop="model_no" />
            <el-table-column label="Status" width="120">
              <template #default="{ row }"><ItemStatusTag :status="row.status" /></template>
            </el-table-column>
            <el-table-column label="Location or holder" min-width="170">
              <template #default="{ row }">{{ row.holder?.display_name ?? row.location.name }}</template>
            </el-table-column>
            <el-table-column label="Warranty ends" width="130">
              <template #default="{ row }">{{ fmtDate(row.warranty_end) }}</template>
            </el-table-column>
            <el-table-column v-for="f in listFields" :key="f.key" :label="f.label" min-width="120">
              <template #default="{ row }">{{ showValue(f, row.attributes[f.key]) }}</template>
            </el-table-column>
          </el-table>
          <el-pagination
            v-if="total > pageSize"
            v-model:current-page="page"
            layout="total, prev, pager, next"
            :total="total"
            :page-size="pageSize"
            class="pager"
          />
          <p v-if="categoryId && !categoryFields.length" class="muted small">This category has no extra fields.</p>
        </el-tab-pane>

        <el-tab-pane label="Deliveries" name="deliveries">
          <el-table :data="deliveries ?? []" :empty-text="deliveries === null ? 'Loading…' : 'No deliveries yet.'">
            <el-table-column label="Delivery" width="150">
              <template #default="{ row }"><span class="mono">{{ row.delivery_no }}</span></template>
            </el-table-column>
            <el-table-column label="Received" width="130">
              <template #default="{ row }">{{ fmtDate(row.received_on) }}</template>
            </el-table-column>
            <el-table-column label="Supplier" min-width="160">
              <template #default="{ row }">{{ row.supplier?.name ?? '—' }}</template>
            </el-table-column>
            <el-table-column label="Delivery order" width="140">
              <template #default="{ row }">{{ row.delivery_order_no ?? '—' }}</template>
            </el-table-column>
            <el-table-column label="Items" width="80" align="right" prop="item_count" />
            <el-table-column label="Store" min-width="150">
              <template #default="{ row }">{{ row.location.name }}</template>
            </el-table-column>
            <el-table-column label="Registered by" min-width="140">
              <template #default="{ row }">{{ row.received_by.display_name }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="History" name="history">
          <el-table :data="history ?? []" :empty-text="history === null ? 'Loading…' : 'Nothing has happened yet.'">
            <el-table-column label="When" width="160">
              <template #default="{ row }">{{ fmtDateTime(row.occurred_at) }}</template>
            </el-table-column>
            <el-table-column label="Item" width="140">
              <template #default="{ row }">
                <RouterLink :to="`/inventory/items/${row.item_id}`" class="mono">{{ row.serial_no }}</RouterLink>
              </template>
            </el-table-column>
            <el-table-column label="What happened" width="170">
              <template #default="{ row }">{{ MOVEMENT_LABEL[row.kind] ?? row.kind }}</template>
            </el-table-column>
            <el-table-column label="Details" min-width="220">
              <template #default="{ row }">{{ describe(row as Movement) || '—' }}</template>
            </el-table-column>
            <el-table-column label="By" min-width="130">
              <template #default="{ row }">{{ row.actor.display_name }}</template>
            </el-table-column>
          </el-table>
          <p class="muted small">The latest 100 changes are shown. Open an item to see its full history.</p>
        </el-tab-pane>
      </el-tabs>
    </section>
  </div>
</template>

<style scoped>
.back {
  font-size: 13px;
  text-decoration: none;
}
.back::before {
  content: '‹ ';
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.small {
  font-size: 12.5px;
}
.warn {
  color: var(--erf-warn);
  font-weight: 600;
}
.table-scroll {
  overflow-x: auto;
}
.summary {
  width: 100%;
  min-width: 640px;
  border-collapse: collapse;
  font-size: 13.5px;
}
.summary th {
  text-align: right;
  font-weight: 500;
  color: var(--erf-muted);
  font-size: 12.5px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--erf-line);
}
.summary td {
  text-align: right;
  padding: 8px 10px;
  border-bottom: 1px solid var(--erf-line);
}
.summary th:first-child,
.summary td:first-child {
  text-align: left;
}
.summary tbody tr:not(.total) {
  cursor: pointer;
}
.summary tbody tr:hover:not(.total) td,
.summary tr.selected td {
  background: color-mix(in srgb, var(--erf-accent) 7%, transparent);
}
.summary tr.total td {
  border-bottom: 0;
}
.summary .empty {
  text-align: left;
}
.filters {
  display: grid;
  gap: 10px;
  margin-bottom: 8px;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chips button {
  font: inherit;
  font-size: 13px;
  padding: 4px 12px;
  border-radius: 999px;
  border: 1px solid var(--erf-line);
  background: var(--erf-surface);
  color: inherit;
  cursor: pointer;
}
.chips button[aria-pressed='true'] {
  background: var(--erf-accent);
  border-color: var(--erf-accent);
  color: #fff;
}
.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.search {
  width: min(320px, 100%);
}
.status-select {
  width: 170px;
}
.pager {
  justify-content: flex-end;
  margin-top: 10px;
}
.clickable :deep(.el-table__row) {
  cursor: pointer;
}
</style>
