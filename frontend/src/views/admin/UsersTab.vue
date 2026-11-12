<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'

import { adminApi, type UserForm } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { AdminTeam, AdminUser, Role } from '@/types/api'
import { errorMessage, fieldErrors, showError, showSuccess } from '@/utils/feedback'
import { fmtDateTime } from '@/utils/format'

import UserImportDialog from './UserImportDialog.vue'

const ROLE_OPTIONS: { value: Role; label: string }[] = [
  { value: 'REQUESTER', label: 'Requester' },
  { value: 'TEAM_LEADER', label: 'Team leader' },
  { value: 'DIRECTOR', label: 'Director' },
  { value: 'ENGINEER', label: 'Engineer' },
  { value: 'INVENTORY_CLERK', label: 'Inventory clerk' },
  { value: 'OPS_MANAGER', label: 'Operations manager' },
  { value: 'VIEWER', label: 'Viewer (reports)' },
  { value: 'ADMIN', label: 'Administrator' },
]
const roleLabel = (r: Role) => ROLE_OPTIONS.find((o) => o.value === r)?.label ?? r

const auth = useAuthStore()
const users = ref<AdminUser[]>([])
const teams = ref<AdminTeam[]>([])
const loading = ref(true)
const search = ref('')
const dialog = ref(false)
const importOpen = ref(false)
const editing = ref<AdminUser | null>(null)
const saving = ref(false)
const errors = ref<Record<string, string>>({})
const formError = ref<string | null>(null)
/** A temporary password to show once, after adding a user or resetting a password. */
const issued = ref<{ name: string; email: string; password: string; reset: boolean } | null>(null)
const form = reactive<UserForm & { email: string; is_active: boolean }>({
  email: '',
  display_name: '',
  job_title: null,
  team_id: null,
  skills: null,
  roles: ['REQUESTER'],
  is_active: true,
})

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  return q
    ? users.value.filter((u) => `${u.display_name} ${u.email} ${u.team?.name ?? ''}`.toLowerCase().includes(q))
    : users.value
})

async function load(): Promise<void> {
  loading.value = true
  try {
    ;[users.value, teams.value] = await Promise.all([adminApi.users(), adminApi.teams()])
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  editing.value = null
  Object.assign(form, { email: '', display_name: '', job_title: null, team_id: null, skills: null, roles: ['REQUESTER'], is_active: true })
  errors.value = {}
  formError.value = null
  dialog.value = true
}

function openEdit(u: AdminUser): void {
  editing.value = u
  Object.assign(form, {
    email: u.email,
    display_name: u.display_name,
    job_title: u.job_title,
    team_id: u.team?.id ?? null,
    skills: u.skills,
    roles: [...u.roles],
    is_active: u.is_active,
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
    if (editing.value) {
      await adminApi.updateUser(editing.value.id, { ...form })
      showSuccess('User updated.')
    } else {
      const result = await adminApi.createUser({ ...form })
      issued.value = { name: result.user.display_name, email: result.user.email, password: result.temporary_password, reset: false }
    }
    dialog.value = false
    await load()
  } catch (e) {
    errors.value = fieldErrors(e)
    formError.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}

async function resetPassword(u: AdminUser): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `${u.display_name}'s current password will stop working immediately and they will be signed out. ` +
        'You will receive a temporary password to give them, and they must choose a new one when they sign in.',
      `Reset the password for ${u.display_name}?`,
      { confirmButtonText: 'Reset password', cancelButtonText: 'Cancel', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    const result = await adminApi.resetPassword(u.id)
    issued.value = { name: result.user.display_name, email: result.user.email, password: result.temporary_password, reset: true }
  } catch (e) {
    showError(e)
  }
}

async function copy(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
    showSuccess('Copied.')
  } catch {
    ElMessage.warning('Copying is not allowed here. Select the password and copy it manually.')
  }
}

onMounted(load)
</script>

<template>
  <div class="tab">
    <div class="bar">
      <el-input v-model="search" placeholder="Search name, email or team" clearable class="search" />
      <div class="bar-actions">
        <el-button @click="importOpen = true">Import from Excel</el-button>
        <el-button type="primary" @click="openCreate">Add user</el-button>
      </div>
    </div>

    <UserImportDialog v-model="importOpen" @imported="load" />

    <el-dialog
      :model-value="!!issued"
      :title="issued?.reset ? 'Password reset' : 'User added'"
      width="min(480px, 94vw)"
      :close-on-click-modal="false"
      @close="issued = null"
    >
      <div v-if="issued" class="issued">
        <p>
          Temporary password for <b>{{ issued.name }}</b> ({{ issued.email }}):
        </p>
        <div class="pw">
          <code>{{ issued.password }}</code>
          <el-button size="small" @click="copy(issued.password)">Copy</el-button>
        </div>
        <p class="muted">
          Give it to the user through a private channel. They must choose their own password when they sign in. This
          password is not shown again; if it is lost, reset the password once more.
        </p>
      </div>
      <template #footer>
        <el-button type="primary" @click="issued = null">Done</el-button>
      </template>
    </el-dialog>

    <el-table v-loading="loading" :data="filtered">
      <el-table-column label="Name" min-width="190">
        <template #default="{ row }">
          <div>{{ row.display_name }} <el-tag v-if="!row.is_active" size="small" type="info">Inactive</el-tag></div>
          <div class="muted small">{{ row.email }}</div>
        </template>
      </el-table-column>
      <el-table-column label="Team" min-width="140">
        <template #default="{ row }">{{ row.team?.name ?? '—' }}</template>
      </el-table-column>
      <el-table-column label="Roles" min-width="220">
        <template #default="{ row }">
          <el-tag v-for="r in row.roles.filter((x: Role) => x !== 'REQUESTER')" :key="r" size="small" class="role">{{ roleLabel(r) }}</el-tag>
          <span v-if="row.roles.length === 1" class="muted">Requester</span>
        </template>
      </el-table-column>
      <el-table-column label="Last sign-in" width="170">
        <template #default="{ row }"><span class="small">{{ fmtDateTime(row.last_login_at) }}</span></template>
      </el-table-column>
      <el-table-column width="190" align="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row as AdminUser)">Edit</el-button>
          <el-tooltip :disabled="row.id !== auth.me?.id" content="Use Change password in your account menu for your own account." placement="left">
            <span class="reset-wrap">
              <el-button size="small" :disabled="row.id === auth.me?.id" @click="resetPassword(row as AdminUser)">Reset password</el-button>
            </span>
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" :title="editing ? `Edit ${editing.display_name}` : 'Add user'" width="min(560px, 94vw)">
      <el-form label-position="top" @submit.prevent="save">
        <el-form-item label="Email" required :error="errors.email" for="u-email">
          <el-input id="u-email" v-model="form.email" :disabled="!!editing" type="email" />
        </el-form-item>
        <el-form-item label="Name" required :error="errors.display_name" for="u-name">
          <el-input id="u-name" v-model="form.display_name" />
        </el-form-item>
        <div class="two">
          <el-form-item label="Job title" for="u-title"><el-input id="u-title" v-model="form.job_title" /></el-form-item>
          <el-form-item label="Team" :error="errors.team_id">
            <el-select v-model="form.team_id" clearable placeholder="No team">
              <el-option v-for="t in teams" :key="t.id" :label="t.name" :value="t.id" />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item label="Roles">
          <el-checkbox-group v-model="form.roles">
            <el-checkbox v-for="o in ROLE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-alert
          v-if="form.roles.includes('TEAM_LEADER')"
          type="info"
          :closable="false"
          show-icon
          class="role-hint"
          title="A team leader receives requests only after being added as an approver in Teams and approvers."
        />
        <el-form-item v-if="form.roles.includes('ENGINEER')" label="Skills (shown to team leaders when assigning)" for="u-skills">
          <el-input id="u-skills" v-model="form.skills" placeholder="e.g. Network, on-site" />
        </el-form-item>
        <el-form-item v-if="editing" label="Status">
          <el-switch v-model="form.is_active" active-text="Active" inactive-text="Inactive" />
        </el-form-item>
        <el-alert v-if="formError" :title="formError" type="error" :closable="false" />
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">Cancel</el-button>
        <el-button type="primary" :loading="saving" @click="save">{{ editing ? 'Save' : 'Add user' }}</el-button>
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
  gap: 10px;
  flex-wrap: wrap;
}
.bar-actions {
  display: flex;
  gap: 10px;
}
.search {
  width: min(320px, 100%);
}
.small {
  font-size: 12px;
}
.role {
  margin: 0 4px 4px 0;
}
.issued p {
  margin: 0 0 12px;
}
.pw {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.pw code {
  font-size: 18px;
  font-family: var(--erf-mono);
  background: var(--erf-surface-2);
  padding: 6px 12px;
  border-radius: 4px;
  user-select: all;
}
.reset-wrap {
  display: inline-block;
  margin-left: 8px;
}
.role-hint {
  margin-bottom: 14px;
}
.two {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 14px;
}
:deep(.el-select) {
  width: 100%;
}
</style>
