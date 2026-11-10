<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { requestApi } from '@/api'
import StatusTag from '@/components/StatusTag.vue'
import UrgentBadge from '@/components/UrgentBadge.vue'
import type { TaskInboxItem } from '@/types/api'
import { showError } from '@/utils/feedback'
import { fmtDate, fmtDateTime, STEP_LABEL } from '@/utils/format'

const router = useRouter()
const items = ref<TaskInboxItem[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    items.value = await requestApi.myTasks()
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
        <p class="sub">Requests waiting for your decision, urgent requests first.</p>
      </div>
    </div>
    <section class="panel">
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
