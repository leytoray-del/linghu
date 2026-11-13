<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { requestApi } from '@/api'
import { inventoryApi } from '@/modules/inventory/api'
import WithdrawalStatusTag from '@/modules/inventory/components/WithdrawalStatusTag.vue'
import type { Withdrawal } from '@/modules/inventory/types'
import { useAuthStore } from '@/stores/auth'
import StatusTag from '@/components/StatusTag.vue'
import UrgentBadge from '@/components/UrgentBadge.vue'
import type { TaskInboxItem } from '@/types/api'
import { showError } from '@/utils/feedback'
import { fmtDate, fmtDateTime, STEP_LABEL } from '@/utils/format'

const router = useRouter()
const auth = useAuthStore()
const items = ref<TaskInboxItem[]>([])
const withdrawals = ref<Withdrawal[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const jobs: Promise<unknown>[] = [requestApi.myTasks().then((t) => (items.value = t))]
    if (auth.can('inventory.view')) jobs.push(inventoryApi.withdrawals('waiting').then((w) => (withdrawals.value = w)))
    await Promise.all(jobs)
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
})

function open(item: TaskInboxItem): void {
  router.push({ name: 'request-detail', params: { id: item.request.id } })
}
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1>Approvals</h1>
        <p class="sub">Everything waiting for your decision: resource requests and equipment withdrawals.</p>
      </div>
    </div>
    <section v-if="withdrawals.length" class="panel">
      <div class="panel-head"><h2>Equipment withdrawals ({{ withdrawals.length }})</h2></div>
      <RouterLink v-for="w in withdrawals" :key="w.id" :to="`/inventory/withdrawals/${w.id}`" class="wrow">
        <span class="mono">{{ w.request_no }}</span>
        <span class="grow">{{ w.item_count }} item{{ w.item_count === 1 ? '' : 's' }} of <b>{{ w.project.name }}</b> to <b>{{ w.to_location.name }}</b> · {{ w.requester.display_name }}</span>
        <WithdrawalStatusTag :status="w.status" />
      </RouterLink>
    </section>
    <section class="panel">
      <div v-if="withdrawals.length" class="panel-head"><h2>Resource requests ({{ items.length }})</h2></div>
      <el-table v-loading="loading" :data="items" row-class-name="clickable-row" empty-text="Nothing is waiting for your decision." @row-click="open">
        <el-table-column label="Request no." width="140">
          <template #default="{ row }"><span class="mono">{{ row.request.display_no }}</span></template>
        </el-table-column>
        <el-table-column label="Project / opportunity" min-width="220">
          <template #default="{ row }">
            <div>{{ row.request.project_name }}</div>
            <div class="muted meta">{{ row.request.requester.display_name }} <UrgentBadge v-if="row.request.is_urgent" /></div>
          </template>
        </el-table-column>
        <el-table-column label="Support" min-width="150">
          <template #default="{ row }">{{ row.request.support_type?.name }} × {{ row.request.headcount }}</template>
        </el-table-column>
        <el-table-column label="Start" width="120">
          <template #default="{ row }">{{ fmtDate(row.request.planned_start) }}</template>
        </el-table-column>
        <el-table-column label="Your step" min-width="170">
          <template #default="{ row }">
            {{ STEP_LABEL[row.step] }}
            <div v-if="row.change_summary" class="muted meta">{{ row.change_summary }}</div>
          </template>
        </el-table-column>
        <el-table-column label="Due" width="190">
          <template #default="{ row }">
            <span :class="{ overdue: row.is_overdue }">{{ fmtDateTime(row.due_at) }}</span>
            <div v-if="row.is_overdue" class="overdue small">Overdue</div>
          </template>
        </el-table-column>
        <el-table-column label="Status" width="210">
          <template #default="{ row }"><StatusTag :status="row.request.status" /></template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<style scoped>
.wrow {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 14px;
  padding: 10px 12px;
  border: 1px solid var(--erf-line);
  border-radius: 8px;
  color: inherit;
  text-decoration: none;
}
.wrow:hover {
  border-color: var(--erf-accent);
}
.grow {
  flex: 1;
  min-width: 200px;
}
.meta {
  font-size: 12px;
  display: flex;
  gap: 6px;
  align-items: center;
}
.overdue {
  color: var(--erf-bad);
}
.small {
  font-size: 12px;
}
</style>
