<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import { adminApi } from '@/api'
import type { OutboxSummary } from '@/types/api'
import { showError, showSuccess } from '@/utils/feedback'
import { fmtDateTime } from '@/utils/format'

const STATUS_TYPE: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
  SENT: 'success',
  PENDING: 'warning',
  FAILED: 'danger',
  SKIPPED: 'info',
}

const data = ref<OutboxSummary | null>(null)
const status = ref<string>('')
const loading = ref(true)

async function load(): Promise<void> {
  loading.value = true
  try {
    data.value = await adminApi.outbox(status.value || undefined)
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}

async function retry(id: number): Promise<void> {
  try {
    await adminApi.retryEmail(id)
    showSuccess('The email will be sent again within a minute.')
    await load()
  } catch (e) {
    showError(e)
  }
}

watch(status, load)
onMounted(load)
</script>

<template>
  <div class="tab">
    <el-alert v-if="data?.backend === 'log'" type="info" :closable="false" show-icon>
      <template #title>Emails are written to the server log instead of being sent</template>
      Set <code>ERF_MAIL_BACKEND=smtp</code> and the SMTP settings on the server to deliver them. The approval workflow
      works the same either way.
    </el-alert>
    <div class="bar">
      <div class="counts">
        <span v-for="(n, s) in data?.counts ?? {}" :key="s"><el-tag :type="STATUS_TYPE[s]" size="small">{{ s }}</el-tag> {{ n }}</span>
      </div>
      <el-select v-model="status" placeholder="All statuses" clearable class="filter">
        <el-option v-for="s in ['PENDING', 'SENT', 'FAILED', 'SKIPPED']" :key="s" :label="s" :value="s" />
      </el-select>
    </div>
    <el-table v-loading="loading" :data="data?.items ?? []" empty-text="No emails yet.">
      <el-table-column label="Created" width="170"><template #default="{ row }"><span class="small">{{ fmtDateTime(row.created_at) }}</span></template></el-table-column>
      <el-table-column label="Subject" min-width="260">
        <template #default="{ row }">
          <div>{{ row.subject }}</div>
          <div class="muted small">To {{ row.to_addresses.join(', ') }}<template v-if="row.cc_addresses.length"> · Cc {{ row.cc_addresses.join(', ') }}</template></div>
          <div v-if="row.last_error" class="error small">{{ row.last_error }}</div>
        </template>
      </el-table-column>
      <el-table-column label="Status" width="120">
        <template #default="{ row }"><el-tag :type="STATUS_TYPE[row.status]" size="small">{{ row.status }}</el-tag></template>
      </el-table-column>
      <el-table-column label="Attempts" width="90" prop="attempts" />
      <el-table-column width="90" align="right">
        <template #default="{ row }">
          <el-button v-if="row.status === 'FAILED'" size="small" @click="retry(row.id)">Retry</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.tab {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.bar {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
}
.counts {
  display: flex;
  gap: 14px;
}
.filter {
  width: 180px;
}
.small {
  font-size: 12px;
}
.error {
  color: var(--erf-bad);
}
</style>
