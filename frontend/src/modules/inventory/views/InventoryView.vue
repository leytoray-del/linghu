<script setup lang="ts">
/**
 * The inventory: every item, filtered by project, kind, location and status. People who may request
 * withdrawals select in-stock items of one project here and request them.
 */
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useMobile } from '@/composables/useMobile'
import { useAuthStore } from '@/stores/auth'
import { showError } from '@/utils/feedback'
import { fmtDate } from '@/utils/format'

import { inventoryApi } from '../api'
import ItemStatusTag from '../components/ItemStatusTag.vue'
import { showValue } from '../format'
import { useInventoryLookups } from '../lookups'
import type { InventorySummary, Item, ItemStatus } from '../types'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const lk = useInventoryLookups()
const { isMobile } = useMobile()

const num = (v: unknown) => (v ? Number(v) : null)
const projectId = ref<number | null>(num(route.query.project))
const categoryId = ref<number | null>(num(route.query.kind))
const locationId = ref<number | null>(num(route.query.location))
const status = ref<ItemStatus | ''>((route.query.status as ItemStatus) || '')
const warranty = ref(route.query.warranty === '1')
const query = ref(String(route.query.q ?? ''))
const page = ref(1)
const pageSize = 50

const items = ref<Item[]>([])
const total = ref(0)
const summary = ref<InventorySummary | null>(null)
const loading = ref(false)
const selected = ref<Item[]>([])

const canWithdraw = computed(() => auth.can('inventory.withdraw'))
const listFields = computed(() => (categoryId.value ? lk.listFields(categoryId.value) : []))
const STATUS_CHIPS: { value: ItemStatus | ''; label: string; key: 'total' | 'in_stock' | 'requested' | 'deployed' }[] = [
  { value: '', label: 'All', key: 'total' },
  { value: 'IN_STOCK', label: 'In stock', key: 'in_stock' },
  { value: 'REQUESTED', label: 'Requested', key: 'requested' },
  { value: 'DEPLOYED', label: 'Deployed', key: 'deployed' },
]

function filter() {
  return {
    project_id: projectId.value ?? undefined,
    category_id: categoryId.value ?? undefined,
    location_id: locationId.value ?? undefined,
    q: query.value.trim() || undefined,
  }
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const [page_, sum] = await Promise.all([
      inventoryApi.items({
        ...filter(),
        status: status.value ? [status.value] : undefined,
        warranty_within_days: warranty.value ? 60 : undefined,
        page: page.value,
        page_size: pageSize,
      }),
      inventoryApi.summary(filter()),
    ])
    items.value = page_.items
    total.value = page_.total
    summary.value = sum
    // Keep the selection only for items still listed and still in stock.
    selected.value = selected.value.filter((s) => page_.items.some((i) => i.id === s.id && i.status === 'IN_STOCK'))
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}

function syncQuery(): void {
  const q: Record<string, string> = {}
  if (projectId.value) q.project = String(projectId.value)
  if (categoryId.value) q.kind = String(categoryId.value)
  if (locationId.value) q.location = String(locationId.value)
  if (status.value) q.status = status.value
  if (warranty.value) q.warranty = '1'
  if (query.value.trim()) q.q = query.value.trim()
  router.replace({ query: q })
}

let timer: number | undefined
watch(query, () => {
  window.clearTimeout(timer)
  timer = window.setTimeout(() => {
    page.value = 1
    syncQuery()
    load()
  }, 300)
})
watch([projectId, categoryId, locationId, status, warranty], () => {
  page.value = 1
  syncQuery()
  load()
})
watch(page, load)

// ---- selecting items for a withdrawal ----

const selectable = (row: Item) => row.status === 'IN_STOCK'
const selectedProject = computed(() => selected.value[0]?.project ?? null)

function onSelect(rows: Item[]): void {
  const projects = new Set(rows.map((r) => r.project.id))
  if (projects.size > 1) {
    ElMessage.warning('A withdrawal is for one project. Choose items of one project only, or filter by project first.')
  }
  selected.value = rows
}

function toggle(row: Item): void {
  if (!selectable(row)) return
  const has = selected.value.some((s) => s.id === row.id)
  if (has) {
    selected.value = selected.value.filter((s) => s.id !== row.id)
  } else if (selectedProject.value && selectedProject.value.id !== row.project.id) {
    ElMessage.warning(`A withdrawal is for one project. ${row.serial_no} belongs to ${row.project.name}.`)
  } else {
    selected.value = [...selected.value, row]
  }
}

function requestSelected(): void {
  const projects = new Set(selected.value.map((r) => r.project.id))
  if (projects.size !== 1) {
    ElMessage.warning('Choose items of one project only.')
    return
  }
  router.push({
    path: '/inventory/withdrawals/new',
    query: { project: String(selectedProject.value!.id), items: selected.value.map((s) => s.id).join(',') },
  })
}

onMounted(async () => {
  try {
    await lk.load()
  } catch (e) {
    showError(e)
  }
  load()
})
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1>Inventory</h1>
        <p class="sub">All equipment, by project. Open an item to see its details and history.</p>
      </div>
      <div class="actions">
        <el-button tag="a" :href="inventoryApi.exportUrl(projectId ?? undefined)">Export to Excel</el-button>
        <el-button v-if="auth.can('inventory.register')" type="primary" @click="$router.push('/inventory/register')">
          Register device
        </el-button>
      </div>
    </div>

    <section class="panel">
      <div class="chips" role="group" aria-label="Status">
        <button
          v-for="c in STATUS_CHIPS"
          :key="c.key"
          type="button"
          :aria-pressed="status === c.value && !warranty"
          @click="(status = c.value), (warranty = false)"
        >
          {{ c.label }} <b class="num">{{ summary?.counts[c.key] ?? '·' }}</b>
        </button>
        <button type="button" class="warn" :aria-pressed="warranty" @click="warranty = !warranty">
          Warranty ends within 60 days <b class="num">{{ summary?.warranty_ending ?? '·' }}</b>
        </button>
      </div>

      <div class="filters">
        <el-input v-model="query" placeholder="Search serial number or any detail" clearable class="search">
          <template #append>
            <el-button aria-label="Scan a label" @click="$router.push('/inventory/scan')">Scan</el-button>
          </template>
        </el-input>
        <el-select v-model="projectId" placeholder="All projects" clearable filterable class="f">
          <el-option v-for="p in lk.data.value?.projects ?? []" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
        <el-select v-model="categoryId" placeholder="All kinds" clearable class="f">
          <el-option v-for="c in lk.data.value?.categories ?? []" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <el-select v-model="locationId" placeholder="All locations" clearable filterable class="f">
          <el-option v-for="l in lk.data.value?.locations ?? []" :key="l.id" :label="l.name" :value="l.id" />
        </el-select>
      </div>

      <div v-if="canWithdraw && selected.length" class="selection" role="status">
        <span><b>{{ selected.length }}</b> selected from {{ selectedProject?.name }}</span>
        <el-button link @click="selected = []">Clear</el-button>
        <el-button type="primary" @click="requestSelected">Request withdrawal</el-button>
      </div>
      <p v-else-if="canWithdraw && !isMobile" class="muted hint">Tick in-stock items of one project to request a withdrawal.</p>

      <!-- Phones: one card per item -->
      <div v-if="isMobile" v-loading="loading" class="cards">
        <div v-for="i in items" :key="i.id" class="card">
          <button
            v-if="canWithdraw && selectable(i)"
            type="button"
            class="tick"
            :aria-pressed="selected.some((s) => s.id === i.id)"
            :aria-label="`Select ${i.serial_no}`"
            @click="toggle(i)"
          >
            ✓
          </button>
          <RouterLink :to="`/inventory/items/${i.id}`" class="card-main">
            <span class="row"><b class="mono">{{ i.serial_no }}</b><ItemStatusTag :status="i.status" /></span>
            <span class="muted">{{ i.category_name }} · {{ i.model_no }}</span>
            <span>{{ i.location.name }}</span>
            <span class="muted small">{{ i.project.name }} · warranty to {{ fmtDate(i.warranty_end) }}</span>
          </RouterLink>
        </div>
        <p v-if="!loading && !items.length" class="muted">No items match.</p>
      </div>

      <!-- Desktop: a table -->
      <el-table
        v-else
        v-loading="loading"
        :data="items"
        row-key="id"
        empty-text="No items match."
        class="clickable"
        @selection-change="onSelect"
        @row-click="(i: Item) => $router.push(`/inventory/items/${i.id}`)"
      >
        <el-table-column v-if="canWithdraw" type="selection" width="44" :selectable="selectable" reserve-selection />
        <el-table-column label="Serial no." min-width="140">
          <template #default="{ row }">
            <RouterLink :to="`/inventory/items/${row.id}`" class="mono" @click.stop>{{ row.serial_no }}</RouterLink>
          </template>
        </el-table-column>
        <el-table-column v-if="!projectId" label="Project" min-width="160">
          <template #default="{ row }">{{ row.project.name }}</template>
        </el-table-column>
        <el-table-column v-if="!categoryId" label="Kind" min-width="100" prop="category_name" />
        <el-table-column label="Model" min-width="95" prop="model_no" />
        <el-table-column label="Status" width="115">
          <template #default="{ row }"><ItemStatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="Location" min-width="170">
          <template #default="{ row }">{{ row.location.name }}</template>
        </el-table-column>
        <el-table-column label="Warranty ends" width="125">
          <template #default="{ row }">{{ fmtDate(row.warranty_end) }}</template>
        </el-table-column>
        <el-table-column v-for="f in listFields" :key="f.key" :label="f.label" min-width="115">
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
    </section>
  </div>
</template>

<style scoped>
.actions,
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.search {
  width: min(360px, 100%);
}
.f {
  width: min(200px, 100%);
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chips button {
  font: inherit;
  font-size: 13.5px;
  padding: 5px 12px;
  border-radius: 999px;
  border: 1px solid var(--erf-line);
  background: var(--erf-surface);
  color: inherit;
  cursor: pointer;
}
.chips button b {
  margin-left: 4px;
}
.chips button[aria-pressed='true'] {
  background: var(--erf-accent);
  border-color: var(--erf-accent);
  color: #fff;
}
.chips button.warn[aria-pressed='true'] {
  background: var(--erf-warn);
  border-color: var(--erf-warn);
}
.selection {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 14px;
  padding: 10px 12px;
  border-radius: var(--erf-radius);
  background: color-mix(in srgb, var(--erf-accent) 8%, var(--erf-surface));
  border: 1px solid color-mix(in srgb, var(--erf-accent) 30%, transparent);
}
.selection .el-button--primary {
  margin-left: auto;
}
.hint {
  margin: 0;
  font-size: 13px;
}
.small {
  font-size: 12.5px;
}
.pager {
  justify-content: flex-end;
}
.clickable :deep(.el-table__row) {
  cursor: pointer;
}
.cards {
  display: grid;
  gap: 8px;
  min-height: 60px;
}
.card {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  border: 1px solid var(--erf-line);
  border-radius: 12px;
  padding: 12px;
  background: var(--erf-surface);
}
.card-main {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 2px;
  color: inherit;
  text-decoration: none;
  font-size: 14px;
}
.card-main .row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}
.tick {
  flex: none;
  width: 28px;
  height: 28px;
  margin-top: 2px;
  border-radius: 8px;
  border: 2px solid var(--erf-line);
  background: var(--erf-surface);
  color: transparent;
  font-weight: 700;
  cursor: pointer;
}
.tick[aria-pressed='true'] {
  background: var(--erf-accent);
  border-color: var(--erf-accent);
  color: #fff;
}
</style>
