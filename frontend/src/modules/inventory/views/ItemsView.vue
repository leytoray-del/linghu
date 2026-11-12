<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { showError } from '@/utils/feedback'
import { fmtDate } from '@/utils/format'

import { inventoryApi } from '../api'
import BarcodeScanner from '../components/BarcodeScanner.vue'
import ItemStatusTag from '../components/ItemStatusTag.vue'
import { ITEM_STATUS_LABEL, showValue } from '../format'
import { useInventoryLookups } from '../lookups'
import type { Item, ItemStatus } from '../types'

/** All items across projects. With `warranty`, it lists warranties that end soon instead. */
const props = defineProps<{ warranty?: boolean }>()

const router = useRouter()
const lk = useInventoryLookups()
const items = ref<Item[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const loading = ref(false)
const query = ref('')
const projectId = ref<number | null>(null)
const categoryId = ref<number | null>(null)
const status = ref<ItemStatus | ''>('')
const withinDays = ref(60)
const scanning = ref(false)

const listFields = computed(() => (categoryId.value ? lk.listFields(categoryId.value) : []))

async function load(): Promise<void> {
  loading.value = true
  try {
    const r = await inventoryApi.items({
      project_id: projectId.value ?? undefined,
      category_id: categoryId.value ?? undefined,
      status: status.value ? [status.value] : undefined,
      q: query.value.trim() || undefined,
      warranty_within_days: props.warranty ? withinDays.value : undefined,
      page: page.value,
      page_size: pageSize,
    })
    items.value = r.items
    total.value = r.total
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}

let timer: number | undefined
watch(query, () => {
  window.clearTimeout(timer)
  timer = window.setTimeout(() => {
    page.value = 1
    load()
  }, 300)
})
watch([projectId, categoryId, status, withinDays, () => props.warranty], () => {
  page.value = 1
  load()
})
watch(page, load)

async function findScanned(code: string): Promise<void> {
  try {
    const check = await inventoryApi.checkSerial(code)
    if (check.exists && check.item_id) {
      scanning.value = false
      await router.push(`/inventory/items/${check.item_id}`)
    } else {
      ElMessage.warning(`${check.serial_no} is not registered.`)
    }
  } catch (e) {
    showError(e)
  }
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
        <h1>{{ warranty ? 'Warranty ending soon' : 'All items' }}</h1>
        <p class="sub">
          {{
            warranty
              ? 'Items in every project whose warranty ends within the chosen period, soonest first.'
              : 'Every item in every project. Search by serial number or any recorded detail, or scan a label to open an item.'
          }}
        </p>
      </div>
      <div class="actions">
        <el-button v-if="!warranty && !scanning" @click="scanning = true">Scan to find</el-button>
        <el-button tag="a" :href="inventoryApi.exportUrl()">Export to Excel</el-button>
      </div>
    </div>

    <section v-if="scanning" class="panel">
      <BarcodeScanner :continuous="true" @code="findScanned" @close="scanning = false" />
    </section>

    <section class="panel">
      <div class="filters">
        <el-input v-if="!warranty" v-model="query" placeholder="Search serial number or any field" clearable class="search" />
        <el-select v-if="warranty" v-model="withinDays" class="narrow" aria-label="Period">
          <el-option :value="30" label="Within 30 days" />
          <el-option :value="60" label="Within 60 days" />
          <el-option :value="90" label="Within 90 days" />
          <el-option :value="180" label="Within 6 months" />
        </el-select>
        <el-select v-model="projectId" placeholder="Any project" clearable filterable class="wide">
          <el-option v-for="p in lk.data.value?.projects ?? []" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
        <el-select v-model="categoryId" placeholder="Any category" clearable class="narrow">
          <el-option v-for="c in lk.data.value?.categories ?? []" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <el-select v-if="!warranty" v-model="status" placeholder="Any status" clearable class="narrow">
          <el-option v-for="(label, key) in ITEM_STATUS_LABEL" :key="key" :label="label" :value="key" />
        </el-select>
      </div>
      <el-table v-loading="loading" :data="items" empty-text="No items match." class="clickable" @row-click="(i: Item) => $router.push(`/inventory/items/${i.id}`)">
        <el-table-column label="Serial no." min-width="140">
          <template #default="{ row }">
            <RouterLink :to="`/inventory/items/${row.id}`" class="mono" @click.stop>{{ row.serial_no }}</RouterLink>
          </template>
        </el-table-column>
        <el-table-column label="Project" min-width="170">
          <template #default="{ row }">{{ row.project.name }}</template>
        </el-table-column>
        <el-table-column label="Category" min-width="110" prop="category_name" />
        <el-table-column label="Model" min-width="100" prop="model_no" />
        <el-table-column label="Status" width="120">
          <template #default="{ row }"><ItemStatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="Location or holder" min-width="160">
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
  width: min(320px, 100%);
}
.wide {
  width: min(240px, 100%);
}
.narrow {
  width: 170px;
}
.pager {
  justify-content: flex-end;
}
.clickable :deep(.el-table__row) {
  cursor: pointer;
}
</style>
