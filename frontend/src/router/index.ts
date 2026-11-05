import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import { setUnauthorizedHandler } from '@/api/http'
import AppLayout from '@/layouts/AppLayout.vue'
import { useAuthStore } from '@/stores/auth'
import type { Role } from '@/types/api'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    public?: boolean
    roles?: Role[]
    /** Custom access check evaluated against the auth store. */
    allow?: (auth: ReturnType<typeof useAuthStore>) => boolean
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/auth/LoginView.vue'),
    meta: { public: true, title: 'Sign in' },
  },
  {
    path: '/',
    component: AppLayout,
    children: [
      { path: '', name: 'dashboard', component: () => import('@/views/dashboard/DashboardView.vue'), meta: { title: 'Dashboard' } },
      { path: 'requests', name: 'requests', component: () => import('@/views/requests/RequestListView.vue'), meta: { title: 'Requests' } },
      { path: 'requests/new', name: 'request-new', component: () => import('@/views/requests/RequestFormView.vue'), meta: { title: 'New request' } },
      { path: 'requests/:id(\\d+)', name: 'request-detail', component: () => import('@/views/requests/RequestDetailView.vue'), meta: { title: 'Request' } },
      { path: 'requests/:id(\\d+)/edit', name: 'request-edit', component: () => import('@/views/requests/RequestFormView.vue'), meta: { title: 'Edit request' } },
      {
        path: 'approvals',
        name: 'approvals',
        component: () => import('@/views/approvals/ApprovalInboxView.vue'),
        meta: { title: 'Approvals', allow: (a) => a.isApprover },
      },
      {
        path: 'resources',
        name: 'resources',
        component: () => import('@/views/resources/ResourceLoadView.vue'),
        meta: { title: 'Resource load', allow: (a) => a.canSeeLoad },
      },
      {
        path: 'reports',
        name: 'reports',
        component: () => import('@/views/reports/ReportsView.vue'),
        meta: { title: 'Reports', allow: (a) => a.canSeeReports },
      },
      {
        path: 'admin',
        name: 'admin',
        component: () => import('@/views/admin/AdminView.vue'),
        meta: { title: 'Settings', roles: ['ADMIN'] },
      },
      {
        path: 'account/password',
        name: 'change-password',
        component: () => import('@/views/account/ChangePasswordView.vue'),
        meta: { title: 'Change password' },
      },
      { path: ':pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFoundView.vue'), meta: { title: 'Not found' } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.ensureLoaded()
  if (to.meta.public) {
    return auth.isSignedIn && to.name === 'login' ? { name: 'dashboard' } : true
  }
  if (!auth.isSignedIn) {
    return { name: 'login', query: to.fullPath !== '/' ? { redirect: to.fullPath } : {} }
  }
  if (auth.me?.must_change_password && to.name !== 'change-password') {
    return { name: 'change-password' }
  }
  if (to.meta.roles && !auth.hasRole(...to.meta.roles)) return { name: 'dashboard' }
  if (to.meta.allow && !to.meta.allow(auth)) return { name: 'dashboard' }
  return true
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · Resource Requests` : 'Resource Requests'
})

setUnauthorizedHandler(() => {
  const auth = useAuthStore()
  if (!auth.isSignedIn) return
  auth.clear()
  const current = router.currentRoute.value
  router.replace({ name: 'login', query: { redirect: current.fullPath, expired: '1' } })
})

export default router
