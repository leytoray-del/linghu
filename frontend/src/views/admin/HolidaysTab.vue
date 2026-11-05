<script setup lang="ts">
import { ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref, watch } from 'vue'

import { adminApi } from '@/api'
import type { AdminHoliday } from '@/types/api'
import { errorMessage, showError, showSuccess } from '@/utils/feedback'
import { fmtDate } from '@/utils/format'

const now = new Date().getFullYear()
const years = [now - 1, now, now + 1]
const year = ref(now)
const holidays = ref<AdminHoliday[]>([])
const loading = ref(true)
const form = reactive({ date: '', name: '' })
const adding = ref(false)
const error = ref<string | null>(null)

async function load(): Promise<void> {
  loading.value = true
  try {
    holidays.value = await adminApi.holidays(year.value)
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}

async function add(): Promise<void> {
  error.value = null
  if (!form.date || !form.name.trim()) {
    error.value = 'Enter both the date and the name of the holiday.'
    return
  }
  adding.value = true
  try {
    await adminApi.addHoliday(form.date, form.name.trim())
    showSuccess('Holiday added. Notice periods for new submissions now exclude it.')
    form.date = ''
    form.name = ''
    await load()
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    adding.value = false
  }
}

async function remove(h: AdminHoliday): Promise<void> {
  try {
    await ElMessageBox.confirm(`Remove ${h.name} on ${fmtDate(h.holiday_date)}?`, 'Remove holiday', {
      confirmButtonText: 'Remove',
      cancelButtonText: 'Keep it',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await adminApi.deleteHoliday(h.id)
    await load()
  } catch (e) {
    showError(e)
  }
}

watch(year, load)
onMounted(load)
</script>

<template>
  <div class="tab">
    <p class="muted intro">
      Public holidays are excluded when the system counts the notice period and approval deadlines. Check the list
      against the official Ministry of Manpower calendar when each new year is published.
    </p>
    <div class="bar">
      <el-radio-group v-model="year" size="small">
        <el-radio-button v-for="y in years" :key="y" :value="y">{{ y }}</el-radio-button>
      </el-radio-group>
      <div class="add">
        <el-date-picker v-model="form.date" type="date" value-format="YYYY-MM-DD" format="D MMM YYYY" placeholder="Date" />
        <el-input v-model="form.name" placeholder="Holiday name" class="name" />
        <el-button type="primary" :loading="adding" @click="add">Add</el-button>
      </div>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-table v-loading="loading" :data="holidays" empty-text="No holidays entered for this year.">
      <el-table-column label="Date" width="160"><template #default="{ row }">{{ fmtDate(row.holiday_date) }}</template></el-table-column>
      <el-table-column label="Day" width="120"><template #default="{ row }">{{ new Date(row.holiday_date).toLocaleDateString('en-GB', { weekday: 'long' }) }}</template></el-table-column>
      <el-table-column prop="name" label="Holiday" />
      <el-table-column width="100" align="right">
        <template #default="{ row }"><el-button size="small" type="danger" plain @click="remove(row as AdminHoliday)">Remove</el-button></template>
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
.intro {
  margin: 0;
  max-width: 70ch;
}
.bar,
.add {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: space-between;
  align-items: center;
}
.name {
  width: 220px;
}
</style>
