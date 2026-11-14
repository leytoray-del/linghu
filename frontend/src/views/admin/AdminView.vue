<script setup lang="ts">
import { type Component, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

import CategoriesTab from '@/modules/inventory/admin/CategoriesTab.vue'
import ModelsTab from '@/modules/inventory/admin/ModelsTab.vue'

import EmailTab from './EmailTab.vue'
import HolidaysTab from './HolidaysTab.vue'
import LocationsTab from './LocationsTab.vue'
import ProjectsTab from './ProjectsTab.vue'
import RolesTab from './RolesTab.vue'
import SettingsTab from './SettingsTab.vue'
import SupportTypesTab from './SupportTypesTab.vue'
import TeamsTab from './TeamsTab.vue'
import UsersTab from './UsersTab.vue'

interface Section {
  key: string
  label: string
  hint: string
  component: Component
}

interface Group {
  title: string
  /** The permission that opens every section of the group. */
  permission: string
  sections: Section[]
}

/** Settings grouped by area. A module adds its own group here. */
const ALL_GROUPS: Group[] = [
  {
    title: 'People and organisation',
    permission: 'core.admin',
    sections: [
      { key: 'users', label: 'Users', hint: 'Accounts, roles and passwords.', component: UsersTab },
      { key: 'roles', label: 'Roles and permissions', hint: 'What each role may see and do. A person gets all the permissions of their roles.', component: RolesTab },
      { key: 'projects', label: 'Projects', hint: 'Projects and their project managers, shared by every module.', component: ProjectsTab },
      { key: 'locations', label: 'Locations', hint: 'Stores, sites and repair centres.', component: LocationsTab },
      { key: 'teams', label: 'Teams and approvers', hint: 'Who reviews requests for each team.', component: TeamsTab },
    ],
  },
  {
    title: 'Resources',
    permission: 'resources.admin',
    sections: [
      { key: 'types', label: 'Types of support', hint: 'The options of "Type of support" and the team each one goes to.', component: SupportTypesTab },
      { key: 'settings', label: 'Workflow rules', hint: 'Notice period, reminders and email link validity.', component: SettingsTab },
      { key: 'holidays', label: 'Public holidays', hint: 'Days that do not count as working days.', component: HolidaysTab },
    ],
  },
  {
    title: 'Inventory',
    permission: 'inventory.admin',
    sections: [
      { key: 'inv-categories', label: 'Kinds of equipment', hint: 'Categories and the fields each one records.', component: CategoriesTab },
      { key: 'inv-models', label: 'Models', hint: 'Device models and their serial number formats.', component: ModelsTab },
    ],
  },
  {
    title: 'System',
    permission: 'core.admin',
    sections: [{ key: 'email', label: 'Email delivery', hint: 'Sending status, test email and retries.', component: EmailTab }],
  },
]
const auth = useAuthStore()
/** Only the groups the person's permissions open. */
const GROUPS = computed(() => ALL_GROUPS.filter((g) => auth.can(g.permission)))
const ALL = computed(() => GROUPS.value.flatMap((g) => g.sections))

const route = useRoute()
const router = useRouter()
const current = computed(() => ALL.value.find((s) => s.key === route.query.section) ?? ALL.value[0]!)

function open(key: string): void {
  router.replace({ query: { ...route.query, section: key } })
}
</script>

<template>
  <div class="page admin">
    <div>
      <h1>Administration</h1>
      <p class="sub">Accounts, projects and locations shared by every module, and the settings of each module.</p>
    </div>
    <div class="layout">
      <nav class="side" aria-label="Administration">
        <div v-for="g in GROUPS" :key="g.title" class="group">
          <span class="group-title">{{ g.title }}</span>
          <button
            v-for="s in g.sections"
            :key="s.key"
            type="button"
            :aria-current="s.key === current.key ? 'page' : undefined"
            @click="open(s.key)"
          >
            {{ s.label }}
          </button>
        </div>
      </nav>
      <el-select class="picker" :model-value="current.key" size="large" aria-label="Administration section" @update:model-value="open">
        <el-option-group v-for="g in GROUPS" :key="g.title" :label="g.title">
          <el-option v-for="s in g.sections" :key="s.key" :label="s.label" :value="s.key" />
        </el-option-group>
      </el-select>
      <section class="panel body">
        <div class="body-head">
          <h2>{{ current.label }}</h2>
          <p class="muted">{{ current.hint }}</p>
        </div>
        <KeepAlive>
          <component :is="current.component" :key="current.key" />
        </KeepAlive>
      </section>
    </div>
  </div>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}
.side {
  position: sticky;
  top: 16px;
  display: grid;
  gap: 14px;
  background: var(--erf-surface);
  border: 1px solid var(--erf-line);
  border-radius: var(--erf-radius);
  padding: 12px 8px;
}
.group {
  display: grid;
  gap: 2px;
}
.group-title {
  font-family: var(--erf-mono);
  font-size: 10.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--erf-muted);
  padding: 0 10px 4px;
}
.side button {
  text-align: left;
  font: inherit;
  color: inherit;
  background: none;
  border: 0;
  border-radius: 6px;
  padding: 7px 10px;
  cursor: pointer;
}
.side button:hover {
  background: var(--erf-surface-2);
}
.side button[aria-current='page'] {
  background: color-mix(in srgb, var(--erf-accent) 10%, transparent);
  color: var(--erf-accent);
  font-weight: 600;
}
.side button:focus-visible {
  outline: 2px solid var(--erf-accent);
  outline-offset: 1px;
}
.picker {
  display: none;
}
.body-head h2 {
  font-size: 17px;
}
.body-head p {
  margin: 4px 0 0;
}
@media (max-width: 860px) {
  .layout {
    grid-template-columns: minmax(0, 1fr);
  }
  .side {
    display: none;
  }
  .picker {
    display: block;
    width: 100%;
  }
}
</style>
