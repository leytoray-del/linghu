<script setup lang="ts">
import { useRouter } from 'vue-router'

import StatusTag from '@/components/StatusTag.vue'
import UrgentBadge from '@/components/UrgentBadge.vue'
import type { RequestSummary } from '@/types/api'
import { fmtDate, TYPE_LABEL } from '@/utils/format'

defineProps<{ rows: RequestSummary[]; loading?: boolean; empty?: string }>()
const router = useRouter()

function open(row: RequestSummary): void {
  router.push({ name: 'request-detail', params: { id: row.id } })
}
</script>

<template>
  <el-table
    v-loading="loading"
    :data="rows"
    row-class-name="clickable-row"
    :empty-text="empty ?? 'No requests to show.'"
    @row-click="open"
  >
    <el-table-column label="Request no." width="140">
      <template #default="{ row }"><span class="mono nowrap">{{ row.display_no }}</span></template>
    </el-table-column>
    <el-table-column label="Project / opportunity" min-width="220">
      <template #default="{ row }">
        <div>{{ row.project_name || '(untitled draft)' }}</div>
        <div class="muted meta">
          {{ row.request_type ? TYPE_LABEL[row.request_type as keyof typeof TYPE_LABEL] : '—' }}
          <UrgentBadge v-if="row.is_urgent" />
        </div>
      </template>
    </el-table-column>
    <el-table-column prop="client_name" label="Client" min-width="100" />
    <el-table-column label="Support" min-width="160">
      <template #default="{ row }">
        {{ row.support_type?.name ?? '—' }}<span v-if="row.headcount"> × {{ row.headcount }}</span>
      </template>
    </el-table-column>
    <el-table-column label="Start" width="120">
      <template #default="{ row }"><span class="nowrap">{{ fmtDate(row.planned_start) }}</span></template>
    </el-table-column>
    <el-table-column label="Notice" width="90">
      <template #default="{ row }">
        <span class="mono">{{ row.notice_working_days ?? '—' }}{{ row.notice_working_days !== null ? ' wd' : '' }}</span>
      </template>
    </el-table-column>
    <el-table-column label="Status" width="210">
      <template #default="{ row }"><StatusTag :status="row.status" /></template>
    </el-table-column>
    <el-table-column label="With" min-width="140">
      <template #default="{ row }">
        {{ row.current_handlers.map((u: { display_name: string }) => u.display_name).join(', ') || '—' }}
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.meta {
  font-size: 12px;
  display: flex;
  gap: 6px;
  align-items: center;
}
</style>
