<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { requestApi } from '@/api'
import RequestTable from '@/components/RequestTable.vue'
import { useAuthStore } from '@/stores/auth'
import type { ListScope, RequestStatus, RequestSummary } from '@/types/api'
import { showError } from '@/utils/feedback'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const SCOPE_LABEL: Record<ListScope, string> = {
  mine: 'My requests',
  team: 'My teams',
  all: 'All requests',
  assigned: 'My assignments',
}

const FILTERS: { key: string; label: string; statuses: RequestStatus[] }[] = [
  { key: 'all', label: 'All', statuses: [] },
  { key: 'open', label: 'In approval', statuses: ['PENDING_TL_REVIEW', 'PENDING_DIRECTOR_APPROVAL'] },
  { key: 'returned', label: 'Rejected, to revise', statuses: ['RETURNED'] },
  { key: 'approved', label: 'Approved', statuses: ['APPROVED'] },
  { key: 'closed', label: 'Finished', statuses: ['CLOSED', 'REJECTED', 'WITHDRAWN', 'CANCELLED'] },
  { key: 'draft', label: 'Drafts', statuses: ['DRAFT'] },
]

const scopes = computed(() => (auth.me?.scopes ?? ['mine']) as ListScope[])
const defaultScope = computed<ListScope>(() =>
  scopes.value.includes('all') ? 'all' : scopes.value.includes('team') ? 'team' : 'mine',
)

const scope = ref<ListScope>(defaultScope.value)
const filter = ref('all')
const urgentOnly = ref(false)
const query = ref('')
const page = ref(1)
const pageSize = 20
const rows = ref<RequestSummary[]>([])
const total = ref(0)
const loading = ref(false)

const visibleFilters = computed(() => FILTERS.filter((f) => f.key !== 'draft' || scope.value === 'mine'))
const statuses = computed(() => FILTERS.find((f) => f.key === filter.value)?.statuses ?? [])

function syncFromRoute(): void {
  const s = route.query.scope as ListScope | undefined
  scope.value = s && scopes.value.includes(s) ? s : defaultScope.value
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const result = await requestApi.list({
      scope: scope.value,
      status: statuses.value,
      urgent: urgentOnly.value,
      q: query.value.trim() || undefined,
      page: page.value,
      page_size: pageSize,
    })
    rows.value = result.items
    total.value = result.total
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}

let searchTimer: number | undefined
watch(query, () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    page.value = 1
    load()
  }, 300)
})
watch([filter, urgentOnly], () => {
  page.value = 1
  load()
})
watch(scope, (s) => {
  if (filter.value === 'draft' && s !== 'mine') filter.value = 'all'
  router.replace({ query: { ...route.query, scope: s } })
  page.value = 1
  load()
})
watch(page, load)

syncFromRoute()
load()

const exportHref = computed(() => requestApi.exportUrl({ scope: scope.value, status: statuses.value }))
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1>Requests</h1>
        <p class="sub">Every request is kept with its complete approval history.</p>
      </div>
      <div class="actions">
        <el-button tag="a" :href="exportHref">Export to Excel</el-button>
        <el-button type="primary" @click="$router.push('/requests/new')">New request</el-button>
      </div>
    </div>

    <div class="toolbar">
      <el-segmented v-if="scopes.length > 1" v-model="scope" :options="scopes.map((s) => ({ label: SCOPE_LABEL[s], value: s }))" />
      <el-input v-model="query" placeholder="Search project, client, number or WBS" clearable class="search" />
    </div>
    <div class="toolbar">
      <el-radio-group v-model="filter" size="small">
        <el-radio-button v-for="f in visibleFilters" :key="f.key" :value="f.key">{{ f.label }}</el-radio-button>
      </el-radio-group>
      <el-checkbox v-model="urgentOnly">Urgent only</el-checkbox>
    </div>

    <section class="panel">
      <RequestTable :rows="rows" :loading="loading" />
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
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.search {
  width: min(340px, 100%);
}
.pager {
  justify-content: flex-end;
}
</style>
