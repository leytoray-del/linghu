<script setup lang="ts">
import { ArrowDown } from '@element-plus/icons-vue'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import InstallHint from '@/components/InstallHint.vue'
import { useMobile } from '@/composables/useMobile'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const navOpen = ref(false)
const { isMobile } = useMobile()
const newSheet = ref(false)
const meSheet = ref(false)

/** Pages reached from the tab bar; every other page shows a back arrow on phones. */
const TAB_ROOTS = new Set(['/', '/approvals', '/requests', '/inventory'])
const isRoot = computed(() => TAB_ROOTS.has(route.path))
/** Task screens (such as registering a delivery or scanning) use the whole phone screen. */
const isFocus = computed(() => route.meta.focus === true)

function goBack(): void {
  if (window.history.state?.back) router.back()
  else router.push(route.path.split('/').slice(0, -1).join('/') || '/')
}

function openFromSheet(to: string): void {
  newSheet.value = false
  meSheet.value = false
  router.push(to)
}

const tabs = computed(() =>
  [
    { key: 'home', to: '/', label: 'Home', show: true },
    auth.isApprover
      ? { key: 'approvals', to: '/approvals', label: 'Approvals', badge: auth.me?.pending_task_count, show: true }
      : { key: 'requests', to: '/requests', label: 'Requests', show: true },
    { key: 'new', to: '', label: 'New', show: true },
    auth.can('inventory.view')
      ? { key: 'scan', to: '/inventory/scan', label: 'Scan', show: true }
      : { key: 'inventory', to: '/inventory', label: 'Inventory', show: false },
    { key: 'me', to: '', label: 'Me', show: true },
  ].filter((t) => t.show),
)

function tabActive(to: string): boolean {
  if (!to) return false
  if (to === '/') return route.path === '/'
  return route.path.startsWith(to)
}

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
      label: 'Register device',
      hint: 'Record devices delivered for a project',
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
    newSheet.value = false
    meSheet.value = false
    if (auth.isSignedIn) auth.refresh().catch(() => {})
  },
)

async function onCommand(command: string): Promise<void> {
  meSheet.value = false
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
      <header v-if="isMobile" class="m-top" :class="{ focus: isFocus }">
        <button v-if="isFocus" type="button" class="m-icon" aria-label="Close" @click="goBack">✕</button>
        <button v-else-if="!isRoot" type="button" class="m-icon" aria-label="Back" @click="goBack">‹</button>
        <span v-else class="m-brand">OpsHub</span>
        <h1 class="m-title">{{ isRoot && route.path === '/' ? '' : route.meta.title }}</h1>
        <span class="m-icon-space" />
      </header>
      <main class="content" :class="{ 'with-tabs': isMobile && !isFocus }">
        <RouterView />
      </main>
    </div>

    <nav v-if="isMobile && !isFocus" class="m-tabs" aria-label="Main">
      <template v-for="t in tabs" :key="t.key">
        <button v-if="t.key === 'new'" type="button" class="m-tab m-new" @click="newSheet = true">
          <span class="m-plus" aria-hidden="true">+</span><span>New</span>
        </button>
        <button v-else-if="t.key === 'me'" type="button" class="m-tab" :aria-expanded="meSheet" @click="meSheet = true">
          <span class="m-glyph" aria-hidden="true">☰</span><span>Me</span>
        </button>
        <RouterLink v-else :to="t.to" class="m-tab" :aria-current="tabActive(t.to) ? 'page' : undefined">
          <span class="m-glyph" aria-hidden="true">{{ t.key === 'home' ? '⌂' : t.key === 'scan' ? '⌗' : t.key === 'approvals' ? '✓' : '≡' }}</span>
          <span>{{ t.label }}</span>
          <span v-if="'badge' in t && t.badge" class="m-badge">{{ t.badge }}</span>
        </RouterLink>
      </template>
    </nav>

    <el-drawer v-if="isMobile" v-model="newSheet" direction="btt" size="auto" :with-header="false" class="m-sheet">
      <div class="sheet-body">
        <h2>Start something</h2>
        <button v-for="n in newItems" :key="n.to" type="button" class="sheet-row" @click="openFromSheet(n.to)">
          <b>{{ n.label }}</b><small>{{ n.hint }}</small>
        </button>
        <el-button size="large" class="sheet-cancel" @click="newSheet = false">Cancel</el-button>
      </div>
    </el-drawer>

    <el-drawer v-if="isMobile" v-model="meSheet" direction="btt" size="88%" :with-header="false" class="m-sheet">
      <div class="sheet-body">
        <div class="me">
          <b>{{ auth.me?.display_name }}</b>
          <small>{{ roleLabel }}{{ auth.me?.team ? ` · ${auth.me.team.name}` : '' }}</small>
          <small>{{ auth.me?.email }}</small>
        </div>
        <InstallHint />
        <div v-for="(g, gi) in groups" :key="gi" class="sheet-group">
          <span class="sheet-title">{{ g.title ?? 'General' }}</span>
          <button v-for="item in g.items" :key="item.to" type="button" class="sheet-link" :aria-current="isActive(item) ? 'page' : undefined" @click="openFromSheet(item.to)">
            <span>{{ item.label }}</span>
            <span v-if="item.badge" class="badge">{{ item.badge }}</span>
          </button>
        </div>
        <div class="sheet-group">
          <span class="sheet-title">Account</span>
          <button type="button" class="sheet-link" @click="onCommand('password')">Change password</button>
          <button type="button" class="sheet-link danger" @click="onCommand('logout')">Sign out</button>
        </div>
      </div>
    </el-drawer>
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
/* Installed on a tablet, the page runs under the status bar. */
@media (min-width: 861px) {
  .rail,
  .topbar {
    padding-top: max(20px, env(safe-area-inset-top, 0px));
  }
}
@media (max-width: 860px) {
  .shell {
    grid-template-columns: minmax(0, 1fr);
    background: none;
  }
  .rail,
  .topbar {
    display: none;
  }
  .content {
    padding: 14px 16px 24px;
  }
  .content.with-tabs {
    padding-bottom: calc(84px + env(safe-area-inset-bottom, 0px));
  }
}

/* ---- phone app layout ---- */
.m-top {
  position: sticky;
  top: 0;
  z-index: 20;
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr) 44px;
  align-items: center;
  gap: 4px;
  padding: calc(env(safe-area-inset-top, 0px) + 6px) 8px 6px;
  background: var(--erf-rail);
  color: #fff;
}
.m-brand {
  font-weight: 700;
  font-size: 16px;
  padding-left: 8px;
  grid-column: 1 / 3;
}
.m-brand + .m-title {
  display: none;
}
.m-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-icon {
  width: 40px;
  height: 40px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: #fff;
  font-size: 26px;
  line-height: 1;
  cursor: pointer;
}
.m-top.focus .m-icon {
  font-size: 20px;
}
.m-icon:active {
  background: var(--erf-rail-active);
}
.m-tabs {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 30;
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: 1fr;
  background: var(--erf-surface);
  border-top: 1px solid var(--erf-line);
  padding: 4px max(4px, env(safe-area-inset-right, 0px)) calc(4px + env(safe-area-inset-bottom, 0px))
    max(4px, env(safe-area-inset-left, 0px));
}
.m-tab {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 6px 0 4px;
  border: 0;
  background: none;
  font: inherit;
  font-size: 11px;
  color: var(--erf-muted);
  text-decoration: none;
  cursor: pointer;
}
.m-tab[aria-current='page'] {
  color: var(--erf-accent);
  font-weight: 600;
}
.m-glyph {
  font-size: 20px;
  line-height: 24px;
}
.m-plus {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  margin-top: -14px;
  border-radius: 50%;
  background: var(--erf-accent);
  color: #fff;
  font-size: 26px;
  line-height: 1;
  box-shadow: 0 4px 12px rgba(34, 84, 197, 0.35);
}
.m-badge {
  position: absolute;
  top: 2px;
  left: calc(50% + 6px);
  min-width: 18px;
  font-size: 11px;
  font-weight: 600;
  line-height: 18px;
  border-radius: 9px;
  background: #e9a94a;
  color: #1b2533;
  padding: 0 5px;
}
.sheet-body {
  display: grid;
  gap: 10px;
  padding-bottom: env(safe-area-inset-bottom, 0px);
}
.sheet-body h2 {
  font-size: 17px;
  margin: 0 0 4px;
}
.sheet-row {
  display: grid;
  gap: 2px;
  text-align: left;
  font: inherit;
  color: inherit;
  background: var(--erf-surface);
  border: 1px solid var(--erf-line);
  border-radius: 12px;
  padding: 14px 16px;
  cursor: pointer;
}
.sheet-row b {
  font-size: 16px;
}
.sheet-row small {
  color: var(--erf-muted);
}
.sheet-cancel {
  width: 100%;
}
.me {
  display: grid;
  gap: 2px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--erf-line);
}
.me b {
  font-size: 17px;
}
.me small {
  color: var(--erf-muted);
}
.sheet-group {
  display: grid;
}
.sheet-title {
  font-family: var(--erf-mono);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--erf-muted);
  padding: 8px 0 4px;
}
.sheet-link {
  display: flex;
  justify-content: space-between;
  align-items: center;
  text-align: left;
  font: inherit;
  font-size: 16px;
  color: inherit;
  background: none;
  border: 0;
  border-bottom: 1px solid var(--erf-line);
  padding: 12px 2px;
  cursor: pointer;
}
.sheet-link[aria-current='page'] {
  color: var(--erf-accent);
  font-weight: 600;
}
.sheet-link.danger {
  color: var(--erf-bad);
}
</style>
