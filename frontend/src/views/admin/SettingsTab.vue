<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { adminApi } from '@/api'
import type { AdminSetting } from '@/types/api'
import { errorMessage, showError, showSuccess } from '@/utils/feedback'

const LABELS: Record<string, string> = {
  min_notice_working_days: 'Minimum notice (working days)',
  tl_due_working_days: 'Team leader deadline (working days)',
  director_due_working_days: 'Director deadline (working days)',
  urgent_due_hours: 'Deadline for urgent requests (hours)',
  reminder_interval_hours: 'Hours between reminders',
  escalate_after_reminders: 'Copy the director from reminder number',
  request_no_prefix: 'Request number prefix',
  email_link_valid_days: 'Email action links valid for (days)',
}

const settings = ref<AdminSetting[]>([])
const drafts = ref<Record<string, string>>({})
const loading = ref(true)
const saving = ref<string | null>(null)
const errors = ref<Record<string, string>>({})

function apply(list: AdminSetting[]): void {
  settings.value = list
  drafts.value = Object.fromEntries(list.map((s) => [s.key, s.value]))
}

async function save(key: string): Promise<void> {
  saving.value = key
  errors.value = {}
  try {
    apply(await adminApi.setSetting(key, drafts.value[key] ?? ''))
    showSuccess('Saved. The new value applies to new submissions and tasks.')
  } catch (e) {
    errors.value = { [key]: errorMessage(e) }
  } finally {
    saving.value = null
  }
}

onMounted(async () => {
  try {
    apply(await adminApi.settings())
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div v-loading="loading" class="tab">
    <div v-for="s in settings" :key="s.key" class="row">
      <div>
        <label :for="`set-${s.key}`"><b>{{ LABELS[s.key] ?? s.key }}</b></label>
        <div class="muted small">{{ s.description }}</div>
      </div>
      <div class="edit">
        <el-input :id="`set-${s.key}`" v-model="drafts[s.key]" class="value" />
        <el-button :disabled="drafts[s.key] === s.value" :loading="saving === s.key" @click="save(s.key)">Save</el-button>
      </div>
      <div v-if="errors[s.key]" class="error small">{{ errors[s.key] }}</div>
    </div>
  </div>
</template>

<style scoped>
.tab {
  display: flex;
  flex-direction: column;
}
.row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 6px 16px;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid var(--erf-line);
}
.edit {
  display: flex;
  gap: 8px;
}
.value {
  width: 110px;
}
.small {
  font-size: 12px;
}
.error {
  color: var(--erf-bad);
  grid-column: 1 / -1;
}
</style>
