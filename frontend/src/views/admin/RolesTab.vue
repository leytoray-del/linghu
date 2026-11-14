<script setup lang="ts">
/**
 * Roles and permissions. A role is a set of permissions, and a person has every permission of every role they hold.
 * Everything is granted this way, including responsibilities such as approving. Every user holds Everyone, so its
 * permissions show as included in every other role. Administrator always has everything except responsibilities.
 */
import { ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import { adminApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { PermissionInfo, RoleInfo } from '@/types/api'
import { errorMessage, fieldErrors, showError, showSuccess } from '@/utils/feedback'

const auth = useAuthStore()
const roles = ref<RoleInfo[]>([])
const catalogue = ref<PermissionInfo[]>([])
const loading = ref(true)
const selected = ref<string | null>(null)
const creating = ref(false)
const form = ref({ name: '', description: '', permissions: [] as string[] })
const errors = ref<Record<string, string>>({})
const formError = ref<string | null>(null)
const saving = ref(false)

const role = computed(() => roles.value.find((r) => r.code === selected.value) ?? null)
const locked = computed(() => !creating.value && !!role.value?.is_locked)
const modules = computed(() => {
  const groups = new Map<string, { name: string; access: PermissionInfo[]; duties: PermissionInfo[] }>()
  for (const p of catalogue.value) {
    if (!groups.has(p.module)) groups.set(p.module, { name: p.module_name, access: [], duties: [] })
    groups.get(p.module)![p.duty ? 'duties' : 'access'].push(p)
  }
  return [...groups.values()]
})
const base = computed(() => roles.value.find((r) => r.is_base))
/** Permissions this role gets from Everyone, which every user holds. */
const inherited = computed(() => (creating.value || !role.value?.is_base ? new Set(base.value?.permissions ?? []) : new Set<string>()))

type BoxState = 'on' | 'off' | 'inherited' | 'admin' | 'not-admin'
function state(p: PermissionInfo): BoxState {
  if (locked.value) return p.duty ? 'not-admin' : 'admin'
  if (form.value.permissions.includes(p.key)) return 'on'
  return inherited.value.has(p.key) ? 'inherited' : 'off'
}
const NOTE: Partial<Record<BoxState, string>> = {
  inherited: 'From Everyone',
  'not-admin': 'Given through other roles',
}
const dirty = computed(() => {
  if (creating.value) return true
  if (!role.value) return false
  return (
    form.value.description !== (role.value.description ?? '') ||
    form.value.name !== role.value.name ||
    [...form.value.permissions].sort().join() !== [...role.value.permissions].sort().join()
  )
})

/** What someone holding only this role (and Everyone) sees, for the preview. Mirrors the menu's own rules. */
const preview = computed(() => {
  const perms = new Set([...form.value.permissions, ...inherited.value])
  if (locked.value) catalogue.value.filter((p) => !p.duty).forEach((p) => perms.add(p.key))
  const has = (p: string) => perms.has(p)
  const resources = [...perms].some((p) => p.startsWith('resources.') && p !== 'resources.admin')
  return {
    menu: [
      ['Home', true],
      ['Approvals', has('resources.review') || has('resources.approve') || has('inventory.approve')],
      ['Resource requests', resources],
      ['Resource load', has('resources.load')],
      ['Inventory', has('inventory.view')],
      ['Withdrawals', has('inventory.view')],
      ['Reports', has('resources.reports')],
      ['Administration', has('core.admin') || has('resources.admin') || has('inventory.admin')],
    ].filter(([, show]) => show).map(([label]) => label as string),
    scoped: (has('resources.load') || has('resources.reports')) && !has('resources.view_all'),
    create: [
      ['Resource request', has('resources.request')],
      ['Register device', has('inventory.register')],
      ['Request withdrawal', has('inventory.withdraw')],
    ].filter(([, show]) => show).map(([label]) => label as string),
    item: [
      ['Edit', has('inventory.edit')],
      ['Delete', has('inventory.delete')],
      ['Return to stock', has('inventory.return')],
    ].filter(([, show]) => show).map(([label]) => label as string),
  }
})

async function load(keep?: string): Promise<void> {
  loading.value = true
  try {
    const data = await adminApi.roles()
    roles.value = data.roles
    catalogue.value = data.permissions
    open(keep ?? selected.value ?? data.roles[1]?.code ?? data.roles[0]!.code)
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}

function open(code: string): void {
  creating.value = false
  selected.value = code
  const r = roles.value.find((x) => x.code === code)
  form.value = { name: r?.name ?? '', description: r?.description ?? '', permissions: [...(r?.permissions ?? [])] }
  errors.value = {}
  formError.value = null
}

function startNew(copyFrom?: RoleInfo): void {
  creating.value = true
  selected.value = null
  form.value = {
    name: copyFrom ? `${copyFrom.name} (copy)` : '',
    description: copyFrom?.description ?? '',
    permissions: copyFrom ? [...copyFrom.permissions] : ['inventory.view'],
  }
  errors.value = {}
  formError.value = null
}

function toggle(key: string, on: boolean): void {
  form.value.permissions = on ? [...new Set([...form.value.permissions, key])] : form.value.permissions.filter((p) => p !== key)
}

async function save(): Promise<void> {
  saving.value = true
  errors.value = {}
  formError.value = null
  try {
    const body = { name: form.value.name.trim(), description: form.value.description.trim() || null, permissions: form.value.permissions }
    const saved = await adminApi.saveRole(body, creating.value ? undefined : role.value!.code)
    showSuccess(creating.value ? `Role ${saved.name} added. Assign it to people on the Users page.` : `${saved.name} saved. The change applies on each person's next page load.`)
    await load(saved.code)
    await auth.refresh()
  } catch (e) {
    errors.value = fieldErrors(e)
    formError.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}

async function remove(): Promise<void> {
  if (!role.value) return
  try {
    await ElMessageBox.confirm(`The role ${role.value.name} will be deleted.`, `Delete ${role.value.name}?`, {
      confirmButtonText: 'Delete',
      cancelButtonText: 'Keep',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await adminApi.deleteRole(role.value.code)
    showSuccess('Role deleted.')
    selected.value = null
    await load()
  } catch (e) {
    showError(e)
  }
}

onMounted(() => load())
</script>

<template>
  <div v-loading="loading" class="roles">
    <aside class="list">
      <button
        v-for="r in roles"
        :key="r.code"
        type="button"
        :aria-current="!creating && r.code === selected ? 'true' : undefined"
        @click="open(r.code)"
      >
        <span class="name">{{ r.name }}</span>
        <span class="meta">
          <span v-if="r.is_locked" class="badge lock">Locked</span>
          <span v-else-if="!r.is_system" class="badge custom">Custom</span>
          <span class="count" :title="`${r.user_count} active users`">{{ r.is_base ? 'All' : r.user_count }}</span>
        </span>
      </button>
      <button type="button" class="add" :aria-current="creating ? 'true' : undefined" @click="startNew()">+ Add role</button>
    </aside>

    <section class="editor">
      <div class="head">
        <div>
          <h3>{{ creating ? 'New role' : role?.name }}</h3>
          <p v-if="!creating && role" class="muted small">
            {{ role.is_base ? 'Every user has this role.' : `${role.user_count} active user${role.user_count === 1 ? '' : 's'}.` }}
            {{ role.is_system && !role.is_locked ? 'System role: it cannot be deleted, but its permissions can be changed.' : '' }}
          </p>
        </div>
        <div class="buttons">
          <el-button v-if="!creating && role && !role.is_locked" @click="startNew(role)">Copy as new role</el-button>
          <el-button v-if="!creating && role && !role.is_system" type="danger" plain @click="remove">Delete</el-button>
        </div>
      </div>

      <el-alert
        v-if="locked"
        type="info"
        :closable="false"
        show-icon
        title="Administrator always has every permission except responsibilities, and cannot be changed."
      >
        <template #default>Responsibilities, such as giving final approval, are given through other roles so that administrators do not receive every approval.</template>
      </el-alert>

      <el-form label-position="top" @submit.prevent>
        <div class="two">
          <el-form-item label="Name" :required="creating" :error="errors.name" for="role-name">
            <el-input id="role-name" v-model="form.name" maxlength="80" :disabled="!creating && role?.is_system" placeholder="For example Store keeper" />
          </el-form-item>
          <el-form-item label="Description" for="role-desc">
            <el-input id="role-desc" v-model="form.description" maxlength="500" :disabled="locked" placeholder="Who this role is for" />
          </el-form-item>
        </div>
      </el-form>

      <div v-for="m in modules" :key="m.name" class="module">
        <h4>{{ m.name }}</h4>
        <template v-for="(list, kind) in { access: m.access, duties: m.duties }" :key="kind">
          <span v-if="kind === 'duties' && list.length" class="sub">Responsibilities</span>
          <label
            v-for="p in list"
            :key="p.key"
            class="perm"
            :class="{ on: ['on', 'admin', 'inherited'].includes(state(p)), fixed: ['admin', 'inherited', 'not-admin'].includes(state(p)) }"
          >
            <el-checkbox
              :model-value="['on', 'admin', 'inherited'].includes(state(p))"
              :disabled="['admin', 'inherited', 'not-admin'].includes(state(p))"
              @update:model-value="(v) => toggle(p.key, !!v)"
            />
            <span>
              <b>{{ p.label }} <em v-if="NOTE[state(p)]">{{ NOTE[state(p)] }}</em></b>
              <small>{{ p.description }}</small>
            </span>
          </label>
        </template>
      </div>

      <div class="preview">
        <h4>What people with this role see</h4>
        <p class="small"><b>Menu:</b> {{ preview.menu.join(' · ') }}</p>
        <p class="small"><b>+ New:</b> {{ preview.create.join(' · ') }}</p>
        <p class="small"><b>On an item:</b> {{ preview.item.length ? preview.item.join(' · ') : 'view only' }}</p>
        <p v-if="preview.scoped" class="muted small">Resource load and reports show only the teams the person reviews, because the role does not see all resource requests.</p>
        <p class="muted small">This includes what everyone can do. A person with several roles gets the permissions of all of them.</p>
      </div>

      <el-alert v-if="formError" :title="formError" type="error" :closable="false" show-icon />
      <div v-if="!locked" class="footer">
        <el-button v-if="creating" @click="open(roles[1]?.code ?? roles[0]!.code)">Cancel</el-button>
        <el-button type="primary" :loading="saving" :disabled="!dirty || (creating && !form.name.trim())" @click="save">
          {{ creating ? 'Add role' : 'Save changes' }}
        </el-button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.roles {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}
@media (max-width: 760px) {
  .roles {
    grid-template-columns: minmax(0, 1fr);
  }
}
.list {
  display: grid;
  gap: 2px;
}
.list button {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  text-align: left;
  font: inherit;
  color: inherit;
  background: none;
  border: 0;
  border-radius: 6px;
  padding: 8px 10px;
  cursor: pointer;
}
.list button:hover {
  background: var(--erf-surface-2);
}
.list button[aria-current='true'] {
  background: color-mix(in srgb, var(--erf-accent) 10%, transparent);
  color: var(--erf-accent);
  font-weight: 600;
}
.list .add {
  color: var(--erf-accent);
  margin-top: 6px;
  border: 1px dashed var(--erf-line);
}
.meta {
  display: flex;
  gap: 6px;
  align-items: center;
}
.count {
  font-size: 12px;
  color: var(--erf-muted);
  font-variant-numeric: tabular-nums;
}
.badge {
  font-size: 10.5px;
  font-weight: 600;
  padding: 0 6px;
  border-radius: 999px;
}
.badge.lock {
  background: var(--erf-surface-2);
  color: var(--erf-muted);
}
.badge.custom {
  background: color-mix(in srgb, var(--erf-ok) 14%, transparent);
  color: var(--erf-ok);
}
.editor {
  display: grid;
  gap: 14px;
  min-width: 0;
}
.head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 10px;
}
.head h3 {
  margin: 0;
  font-size: 17px;
}
.small {
  font-size: 13px;
  margin: 2px 0 0;
}
.buttons,
.footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.buttons .el-button + .el-button,
.footer .el-button + .el-button {
  margin-left: 0;
}
.footer {
  justify-content: flex-end;
}
.two {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 0 16px;
}
.module {
  display: grid;
  gap: 4px;
}
.module h4,
.preview h4 {
  margin: 0 0 4px;
  font-size: 12px;
  font-family: var(--erf-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--erf-muted);
}
.perm {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 8px 10px;
  border: 1px solid var(--erf-line);
  border-radius: 8px;
  cursor: pointer;
}
.perm.on {
  border-color: color-mix(in srgb, var(--erf-accent) 45%, transparent);
  background: color-mix(in srgb, var(--erf-accent) 5%, transparent);
}
.perm.fixed {
  cursor: default;
}
.perm em {
  font-style: normal;
  font-weight: 500;
  font-size: 11px;
  color: var(--erf-muted);
  margin-left: 6px;
}
.sub {
  font-size: 12px;
  font-weight: 600;
  color: var(--erf-muted);
  margin: 6px 0 0;
}
.perm span {
  display: grid;
  gap: 1px;
}
.perm small {
  color: var(--erf-muted);
  font-size: 12.5px;
}
.perm :deep(.el-checkbox) {
  height: auto;
  margin-top: 1px;
}
.preview {
  background: var(--erf-surface-2);
  border-radius: 8px;
  padding: 10px 12px;
}
</style>
