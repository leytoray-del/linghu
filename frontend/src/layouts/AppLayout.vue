<script setup lang="ts">
import { ArrowDown } from '@element-plus/icons-vue'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const navOpen = ref(false)

interface NavItem {
  to: string
  label: string
  badge?: number
  show: boolean
}

interface NavGroup {
  /** Section heading; the first group has none. */
  title?: string
  /** Module colour shown beside the heading. */
  tone?: 'res' | 'inv'
  items: NavItem[]
}

/**
 * The menu is organised by the person's work first (Home, Approvals), then by module.
 * A module adds its own group; a group with nothing the user may open is hidden.
 */
const groups = computed<NavGroup[]>(() =>
  [
    {
      items: [
        { to: '/', label: 'Home', show: true },
        { to: '/approvals', label: 'Approvals', badge: auth.me?.pending_task_count, show: auth.isApprover },
      ],
    },
    {
      title: 'Resources',
      tone: 'res' as const,
      items: [
        { to: '/requests', label: 'Resource requests', show: true },
        { to: '/resources', label: 'Resource load', show: auth.canSeeLoad },
      ],
    },
    {
      title: 'Inventory',
      tone: 'inv' as const,
      items: [
        { to: '/inventory', label: 'Project inventory', show: auth.can('inventory.view') },
        { to: '/inventory/items', label: 'All items', show: auth.can('inventory.view') },
        { to: '/inventory/warranty', label: 'Warranty', show: auth.can('inventory.view') },
      ],
    },
    {
      title: 'Insights',
      items: [{ to: '/reports', label: 'Reports', show: auth.canSeeReports }],
    },
    {
      title: 'System',
      items: [{ to: '/admin', label: 'Administration', show: auth.hasRole('ADMIN') }],
    },
  ]
    .map((g) => ({ ...g, items: g.items.filter((i) => i.show) }))
    .filter((g) => g.items.length),
)

/** Everything the user may start, from any module. */
const newItems = computed(() =>
  [
    { to: '/requests/new', label: 'Resource request', hint: 'Ask for engineers for a project', show: true },
    {
      to: '/inventory/deliveries/new',
      label: 'Register delivery',
      hint: 'Record equipment delivered for a project',
      show: auth.can('inventory.register'),
    },
  ].filter((i) => i.show),
)

function isActive(item: NavItem): boolean {
  const path = route.path
  if (item.to === '/') return path === '/'
  if (item.to === '/requests') return path.startsWith('/requests')
  if (item.to === '/inventory') return path === '/inventory' || path.startsWith('/inventory/projects')
  if (item.to === '/inventory/items') return path.startsWith('/inventory/items')
  return path.startsWith(item.to)
}

const roleLabel = computed(() => {
  const names: Record<string, string> = {
    ADMIN: 'Administrator',
    DIRECTOR: 'Director',
    TEAM_LEADER: 'Team leader',
    ENGINEER: 'Engineer',
    VIEWER: 'Viewer',
    INVENTORY_CLERK: 'Inventory clerk',
    OPS_MANAGER: 'Operations manager',
  }
  const shown = (auth.me?.roles ?? []).filter((r) => r in names).map((r) => names[r])
  return shown.length ? shown.join(', ') : 'Requester'
})

// Keep the approvals badge current as the user moves around.
watch(
  () => route.fullPath,
  () => {
    navOpen.value = false
    if (auth.isSignedIn) auth.refresh().catch(() => {})
  },
)

async function onCommand(command: string): Promise<void> {
  if (command === 'password') {
    await router.push({ name: 'change-password' })
  } else if (command === 'logout') {
    await auth.logout()
    await router.replace({ name: 'login' })
  }
}
</script>

<template>
  <div class="shell">
    <aside class="rail" :class="{ open: navOpen }">
      <div class="brand">
        <b>OpsHub</b>
        <span>PSBU Engineering Operations</span>
      </div>
      <button class="menu-toggle" type="button" :aria-expanded="navOpen" @click="navOpen = !navOpen">Menu</button>
      <nav class="nav" aria-label="Main">
        <el-dropdown trigger="click" class="new" @command="(to: string) => router.push(to)">
          <button type="button" class="new-btn">+ New</button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-for="n in newItems" :key="n.to" :command="n.to">
                <span class="new-item"><b>{{ n.label }}</b><small>{{ n.hint }}</small></span>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <div v-for="(g, gi) in groups" :key="gi" class="group">
          <span v-if="g.title" class="group-title"><i v-if="g.tone" :class="`tone-${g.tone}`" />{{ g.title }}</span>
          <RouterLink v-for="item in g.items" :key="item.to" :to="item.to" :aria-current="isActive(item) ? 'page' : undefined">
            <span>{{ item.label }}</span>
            <span v-if="item.badge" class="badge">{{ item.badge }}</span>
          </RouterLink>
        </div>
      </nav>
    </aside>
    <div class="main">
      <header class="topbar">
        <div class="crumb">{{ route.meta.title }}</div>
        <el-dropdown trigger="click" @command="onCommand">
          <button class="user" type="button">
            <span class="who">
              <b>{{ auth.me?.display_name }}</b>
              <small>{{ roleLabel }}{{ auth.me?.team ? ` · ${auth.me.team.name}` : '' }}</small>
            </span>
            <el-icon><ArrowDown /></el-icon>
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item disabled>{{ auth.me?.email }}</el-dropdown-item>
              <el-dropdown-item command="password" divided>Change password</el-dropdown-item>
              <el-dropdown-item command="logout">Sign out</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </header>
      <main class="content">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 228px minmax(0, 1fr);
  min-height: 100%;
  /* Paint the navigation column for the full page height; the rail itself is sticky. */
  background: linear-gradient(to right, var(--erf-rail) 228px, transparent 228px);
}
.rail {
  background: var(--erf-rail);
  color: var(--erf-rail-fg);
  padding: 20px 14px;
  display: flex;
  flex-direction: column;
  gap: 22px;
  position: sticky;
  top: 0;
  height: 100vh;
}
.brand {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 8px;
}
.brand b {
  color: #fff;
  font-size: 15px;
}
.brand span {
  font-family: var(--erf-mono);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  opacity: 0.7;
}
.menu-toggle {
  display: none;
}
.nav {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.group-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: var(--erf-mono);
  font-size: 10.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  opacity: 0.6;
  padding: 0 10px 4px;
}
.group-title i {
  width: 7px;
  height: 7px;
  border-radius: 2px;
}
.tone-res {
  background: #5b8def;
}
.tone-inv {
  background: #2fbf9a;
}
.new {
  display: block;
}
.new-btn {
  width: 100%;
  border: 0;
  border-radius: var(--erf-radius);
  background: var(--erf-accent);
  color: #fff;
  font: inherit;
  font-weight: 600;
  padding: 8px 10px;
  cursor: pointer;
}
.new-btn:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 2px;
}
.new-item {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
  padding: 2px 0;
}
.new-item small {
  color: var(--erf-muted);
}
.nav a {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 10px;
  border-radius: var(--erf-radius);
  color: var(--erf-rail-fg);
  text-decoration: none;
}
.nav a:hover {
  background: var(--erf-rail-active);
  color: #fff;
}
.nav a[aria-current='page'] {
  background: var(--erf-rail-active);
  color: #fff;
  font-weight: 600;
}
.badge {
  font-family: var(--erf-mono);
  font-size: 11px;
  background: #e9a94a;
  color: #1b2533;
  border-radius: 10px;
  padding: 0 7px;
}
.main {
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 24px;
  background: var(--erf-surface);
  border-bottom: 1px solid var(--erf-line);
}
.crumb {
  color: var(--erf-muted);
  font-size: 13px;
}
.user {
  display: flex;
  align-items: center;
  gap: 10px;
  background: none;
  border: 0;
  cursor: pointer;
  text-align: right;
  color: inherit;
  font: inherit;
}
.who {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}
.who small {
  color: var(--erf-muted);
  font-size: 12px;
}
.content {
  padding: 24px 24px 48px;
}
@media (max-width: 860px) {
  .shell {
    grid-template-columns: minmax(0, 1fr);
    background: none;
  }
  .rail {
    position: static;
    height: auto;
    flex-direction: row;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    gap: 10px;
  }
  .menu-toggle {
    display: inline-block;
    background: var(--erf-rail-active);
    color: #fff;
    border: 0;
    border-radius: var(--erf-radius);
    padding: 6px 12px;
    font: inherit;
  }
  .nav {
    display: none;
    width: 100%;
  }
  .rail.open .nav {
    display: flex;
  }
  .topbar,
  .content {
    padding-left: 16px;
    padding-right: 16px;
  }
}
</style>
