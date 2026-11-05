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

const nav = computed<NavItem[]>(() => [
  { to: '/', label: 'Dashboard', show: true },
  { to: '/requests/new', label: 'New request', show: true },
  { to: '/requests', label: 'Requests', show: true },
  { to: '/approvals', label: 'Approvals', badge: auth.me?.pending_task_count, show: auth.isApprover },
  { to: '/resources', label: 'Resource load', show: auth.canSeeLoad },
  { to: '/reports', label: 'Reports', show: auth.canSeeReports },
  { to: '/admin', label: 'Settings', show: auth.hasRole('ADMIN') },
])

function isActive(item: NavItem): boolean {
  if (item.to === '/') return route.path === '/'
  if (item.to === '/requests') return route.path.startsWith('/requests') && route.path !== '/requests/new'
  return route.path.startsWith(item.to)
}

const roleLabel = computed(() => {
  const names: Record<string, string> = {
    ADMIN: 'Administrator',
    DIRECTOR: 'Director',
    TEAM_LEADER: 'Team leader',
    ENGINEER: 'Engineer',
    VIEWER: 'Viewer',
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
        <b>Resource Requests</b>
        <span>Engineering</span>
      </div>
      <button class="menu-toggle" type="button" :aria-expanded="navOpen" @click="navOpen = !navOpen">Menu</button>
      <nav class="nav" aria-label="Main">
        <template v-for="item in nav" :key="item.to">
          <RouterLink v-if="item.show" :to="item.to" :aria-current="isActive(item) ? 'page' : undefined">
            <span>{{ item.label }}</span>
            <span v-if="item.badge" class="badge">{{ item.badge }}</span>
          </RouterLink>
        </template>
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
  gap: 2px;
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
