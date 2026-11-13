<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { useAuthStore } from '@/stores/auth'
import { showError } from '@/utils/feedback'

import { inventoryApi } from '../api'
import type { ProjectInventoryRow } from '../types'

const auth = useAuthStore()
const rows = ref<ProjectInventoryRow[]>([])
const loading = ref(true)
const query = ref('')
const showClosed = ref(false)

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return rows.value.filter(
    (r) =>
      (showClosed.value || r.project.is_active) &&
      (!q || `${r.project.name} ${r.project.code} ${r.project.client_name ?? ''} ${r.project.pm?.display_name ?? ''}`.toLowerCase().includes(q)),
  )
})
const totals = computed(() =>
  filtered.value.reduce(
    (t, r) => ({
      total: t.total + r.counts.total,
      in_stock: t.in_stock + r.counts.in_stock,
      deployed: t.deployed + r.counts.deployed,
      attention: t.attention + r.counts.faulty + r.counts.in_repair,
      warranty: t.warranty + r.warranty_ending,
    }),
    { total: 0, in_stock: 0, deployed: 0, attention: 0, warranty: 0 },
  ),
)

onMounted(async () => {
  try {
    rows.value = await inventoryApi.projects()
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1>Project inventory</h1>
        <p class="sub">Equipment is kept under the project it was delivered for. Open a project to see and manage its items.</p>
      </div>
      <div class="actions">
        <el-button tag="a" :href="inventoryApi.exportUrl()">Export all to Excel</el-button>
        <el-button v-if="auth.can('inventory.register')" type="primary" @click="$router.push('/inventory/deliveries/new')">
          Register device
        </el-button>
      </div>
    </div>

    <div class="tiles">
      <div class="tile"><span class="label">Items</span><span class="value num">{{ totals.total }}</span></div>
      <div class="tile"><span class="label">In stock</span><span class="value num">{{ totals.in_stock }}</span></div>
      <div class="tile"><span class="label">Deployed</span><span class="value num">{{ totals.deployed }}</span></div>
      <div class="tile" :class="{ attention: totals.attention }">
        <span class="label">Faulty or in repair</span><span class="value num">{{ totals.attention }}</span>
      </div>
      <div class="tile" :class="{ attention: totals.warranty }">
        <span class="label">Warranty ends within 60 days</span><span class="value num">{{ totals.warranty }}</span>
      </div>
    </div>

    <section class="panel">
      <div class="panel-head">
        <el-input v-model="query" placeholder="Search project, WBS code, client or PM" clearable class="search" />
        <el-checkbox v-model="showClosed">Show closed projects</el-checkbox>
      </div>
      <el-table
        v-loading="loading"
        :data="filtered"
        empty-text="No projects yet. An administrator adds projects in Settings."
        class="clickable"
        @row-click="(r: ProjectInventoryRow) => $router.push(`/inventory/projects/${r.project.id}`)"
      >
        <el-table-column label="Project" min-width="240">
          <template #default="{ row }">
            <RouterLink :to="`/inventory/projects/${row.project.id}`" class="name" @click.stop>{{ row.project.name }}</RouterLink>
            <div class="muted small">
              <span class="mono">{{ row.project.code }}</span>
              <template v-if="row.project.client_name"> · {{ row.project.client_name }}</template>
              <el-tag v-if="!row.project.is_active" size="small" type="info" class="closed">Closed</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="PM" min-width="140">
          <template #default="{ row }">{{ row.project.pm?.display_name ?? '—' }}</template>
        </el-table-column>
        <el-table-column label="Items" width="90" align="right">
          <template #default="{ row }"><b class="num">{{ row.counts.total }}</b></template>
        </el-table-column>
        <el-table-column label="In stock" width="95" align="right">
          <template #default="{ row }"><span class="num">{{ row.counts.in_stock }}</span></template>
        </el-table-column>
        <el-table-column label="Out" width="80" align="right">
          <template #default="{ row }"><span class="num">{{ row.counts.reserved + row.counts.issued }}</span></template>
        </el-table-column>
        <el-table-column label="Deployed" width="100" align="right">
          <template #default="{ row }"><span class="num">{{ row.counts.deployed }}</span></template>
        </el-table-column>
        <el-table-column label="Faulty or in repair" width="150" align="right">
          <template #default="{ row }">
            <span class="num" :class="{ bad: row.counts.faulty + row.counts.in_repair }">{{ row.counts.faulty + row.counts.in_repair }}</span>
          </template>
        </el-table-column>
        <el-table-column label="Warranty ending" width="140" align="right">
          <template #default="{ row }">
            <span class="num" :class="{ warn: row.warranty_ending }">{{ row.warranty_ending }}</span>
          </template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<style scoped>
.tiles {
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.search {
  width: min(360px, 100%);
}
.name {
  font-weight: 600;
  text-decoration: none;
}
.small {
  font-size: 12.5px;
}
.closed {
  margin-left: 6px;
}
.bad {
  color: var(--erf-bad);
  font-weight: 600;
}
.warn {
  color: var(--erf-warn);
  font-weight: 600;
}
.clickable :deep(.el-table__row) {
  cursor: pointer;
}
</style>
