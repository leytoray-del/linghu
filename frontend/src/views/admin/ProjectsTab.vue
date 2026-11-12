<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { adminApi, orgApi } from '@/api'
import type { AdminUser, Project } from '@/types/api'
import { errorMessage, fieldErrors, showError, showSuccess } from '@/utils/feedback'

const projects = ref<Project[]>([])
const users = ref<AdminUser[]>([])
const loading = ref(true)
const dialog = ref(false)
const editing = ref<Project | null>(null)
const saving = ref(false)
const errors = ref<Record<string, string>>({})
const formError = ref<string | null>(null)
const search = ref('')
const form = reactive({ code: '', name: '', client_name: '', pm_user_id: null as number | null, remarks: '', is_active: true })

const activeUsers = computed(() => users.value.filter((u) => u.is_active))
const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  return q
    ? projects.value.filter((p) => `${p.name} ${p.code} ${p.client_name ?? ''} ${p.pm?.display_name ?? ''}`.toLowerCase().includes(q))
    : projects.value
})

async function load(): Promise<void> {
  loading.value = true
  try {
    ;[projects.value, users.value] = await Promise.all([orgApi.projects(), adminApi.users()])
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}

function open(row: Project | null): void {
  editing.value = row
  Object.assign(form, {
    code: row?.code ?? '',
    name: row?.name ?? '',
    client_name: row?.client_name ?? '',
    pm_user_id: row?.pm?.id ?? null,
    remarks: row?.remarks ?? '',
    is_active: row?.is_active ?? true,
  })
  errors.value = {}
  formError.value = null
  dialog.value = true
}

async function save(): Promise<void> {
  saving.value = true
  errors.value = {}
  formError.value = null
  try {
    await orgApi.saveProject(
      { ...form, client_name: form.client_name.trim() || null, remarks: form.remarks.trim() || null },
      editing.value?.id,
    )
    showSuccess('Project saved.')
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
        Projects are shared by every module. Inventory is kept under them, and the project manager named here will approve
        equipment withdrawals for the project. Close a project instead of deleting it, so its records stay.
      </p>
      <el-button type="primary" @click="open(null)">Add project</el-button>
    </div>
    <el-input v-model="search" placeholder="Search name, WBS code, client or PM" clearable class="search" />
    <el-table v-loading="loading" :data="filtered">
      <el-table-column prop="name" label="Project" min-width="200" />
      <el-table-column label="WBS code" width="130"><template #default="{ row }"><span class="mono">{{ row.code }}</span></template></el-table-column>
      <el-table-column label="Client" min-width="120"><template #default="{ row }">{{ row.client_name ?? '—' }}</template></el-table-column>
      <el-table-column label="Project manager" min-width="150">
        <template #default="{ row }"><span :class="{ warn: !row.pm }">{{ row.pm?.display_name ?? 'Not set' }}</span></template>
      </el-table-column>
      <el-table-column label="Status" width="100">
        <template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? 'Active' : 'Closed' }}</el-tag></template>
      </el-table-column>
      <el-table-column width="90" align="right">
        <template #default="{ row }"><el-button size="small" @click="open(row as Project)">Edit</el-button></template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" :title="editing ? `Edit ${editing.name}` : 'Add project'" width="min(520px, 94vw)">
      <el-form label-position="top" @submit.prevent="save">
        <el-form-item label="Project name" required :error="errors.name" for="pj-name"><el-input id="pj-name" v-model="form.name" maxlength="200" /></el-form-item>
        <el-form-item label="WBS code" required :error="errors.code" for="pj-code"><el-input id="pj-code" v-model="form.code" maxlength="64" /></el-form-item>
        <el-form-item label="Client" :error="errors.client_name" for="pj-client"><el-input id="pj-client" v-model="form.client_name" maxlength="200" /></el-form-item>
        <el-form-item label="Project manager" :error="errors.pm_user_id">
          <el-select v-model="form.pm_user_id" filterable clearable placeholder="Choose a person">
            <el-option v-for="u in activeUsers" :key="u.id" :label="`${u.display_name} (${u.email})`" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="Remarks" for="pj-remarks"><el-input id="pj-remarks" v-model="form.remarks" type="textarea" :autosize="{ minRows: 2 }" /></el-form-item>
        <el-form-item label="Status"><el-switch v-model="form.is_active" active-text="Active" inactive-text="Closed" /></el-form-item>
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
.search {
  width: min(340px, 100%);
}
.warn {
  color: var(--erf-warn);
}
:deep(.el-select) {
  width: 100%;
}
</style>
