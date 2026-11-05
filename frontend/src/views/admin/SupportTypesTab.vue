<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { adminApi } from '@/api'
import type { AdminSupportType, AdminTeam } from '@/types/api'
import { errorMessage, fieldErrors, showError, showSuccess } from '@/utils/feedback'

const types = ref<AdminSupportType[]>([])
const teams = ref<AdminTeam[]>([])
const loading = ref(true)
const dialog = ref(false)
const editing = ref<AdminSupportType | null>(null)
const saving = ref(false)
const errors = ref<Record<string, string>>({})
const formError = ref<string | null>(null)
const form = reactive({ code: '', name: '', team_id: 0, sort_order: 0, is_active: true })

const teamName = (id: number) => teams.value.find((t) => t.id === id)?.name ?? '—'

async function load(): Promise<void> {
  loading.value = true
  try {
    ;[types.value, teams.value] = await Promise.all([adminApi.supportTypes(), adminApi.teams()])
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}

function open(row: AdminSupportType | null): void {
  editing.value = row
  Object.assign(
    form,
    row ?? { code: '', name: '', team_id: teams.value[0]?.id ?? 0, sort_order: (types.value.length + 1) * 10, is_active: true },
  )
  errors.value = {}
  formError.value = null
  dialog.value = true
}

async function save(): Promise<void> {
  saving.value = true
  errors.value = {}
  formError.value = null
  try {
    await adminApi.saveSupportType({ ...form, code: form.code.trim().toUpperCase() }, editing.value?.id)
    showSuccess('Type of support saved.')
    dialog.value = false
    await load()
  } catch (e) {
    errors.value = fieldErrors(e)
    formError.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="tab">
    <div class="bar">
      <p class="muted intro">
        These are the options of the "Type of support" field. Each one decides which team reviews the request. Deactivate
        an option instead of deleting it, so that old requests keep their history.
      </p>
      <el-button type="primary" @click="open(null)">Add type</el-button>
    </div>
    <el-table v-loading="loading" :data="types">
      <el-table-column prop="name" label="Name" min-width="180" />
      <el-table-column label="Code" width="120"><template #default="{ row }"><span class="mono">{{ row.code }}</span></template></el-table-column>
      <el-table-column label="Routed to" min-width="160"><template #default="{ row }">{{ teamName(row.team_id) }}</template></el-table-column>
      <el-table-column prop="sort_order" label="Order" width="90" />
      <el-table-column label="Status" width="110">
        <template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? 'Active' : 'Inactive' }}</el-tag></template>
      </el-table-column>
      <el-table-column width="90" align="right">
        <template #default="{ row }"><el-button size="small" @click="open(row as AdminSupportType)">Edit</el-button></template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" :title="editing ? `Edit ${editing.name}` : 'Add type of support'" width="min(480px, 94vw)">
      <el-form label-position="top" @submit.prevent="save">
        <el-form-item label="Name" required :error="errors.name" for="st-name"><el-input id="st-name" v-model="form.name" /></el-form-item>
        <el-form-item label="Code (capital letters, digits and underscores)" required :error="errors.code" for="st-code">
          <el-input id="st-code" v-model="form.code" />
        </el-form-item>
        <el-form-item label="Routed to team" required :error="errors.team_id">
          <el-select v-model="form.team_id">
            <el-option v-for="t in teams" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="Display order" for="st-order"><el-input-number id="st-order" v-model="form.sort_order" :step="10" /></el-form-item>
        <el-form-item label="Status"><el-switch v-model="form.is_active" active-text="Active" inactive-text="Inactive" /></el-form-item>
        <el-alert v-if="formError" :title="formError" type="error" :closable="false" />
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">Cancel</el-button>
        <el-button type="primary" :loading="saving" @click="save">Save</el-button>
      </template>
    </el-dialog>
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
  align-items: flex-start;
  gap: 14px;
  flex-wrap: wrap;
}
.intro {
  margin: 0;
  max-width: 70ch;
}
:deep(.el-select) {
  width: 100%;
}
</style>
