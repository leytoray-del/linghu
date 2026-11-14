import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { authApi } from '@/api'
import type { ListScope, Me, Role } from '@/types/api'

export const useAuthStore = defineStore('auth', () => {
  const me = ref<Me | null>(null)
  const loaded = ref(false)

  const isSignedIn = computed(() => me.value !== null)

  function hasRole(...roles: Role[]): boolean {
    return !!me.value && roles.some((r) => me.value!.roles.includes(r))
  }

  /** Whether the user's roles grant a permission, such as inventory.register. */
  function can(permission: string): boolean {
    return !!me.value && me.value.permissions.includes(permission)
  }

  function hasScope(scope: ListScope): boolean {
    return !!me.value && me.value.scopes.includes(scope)
  }

  /** Reviews at least one team (the server only lists teams of people who may review). */
  const isTeamLeader = computed(() => (me.value?.led_team_ids.length ?? 0) > 0)
  /** Load and reports cover all teams with "See all resource requests", otherwise the teams one reviews. */
  const canSeeReports = computed(() => can('resources.reports') && (can('resources.view_all') || isTeamLeader.value))
  const canSeeLoad = computed(() => can('resources.load') && (can('resources.view_all') || isTeamLeader.value))
  /** The Resource requests menu: anyone who raises, sees, reviews, approves or is assigned to requests. */
  const canSeeRequests = computed(() => !!me.value?.permissions.some((p) => p.startsWith('resources.') && p !== 'resources.admin'))
  const isApprover = computed(() => isTeamLeader.value || can('resources.approve'))
  const showApprovals = computed(
    () =>
      isApprover.value ||
      can('inventory.approve') ||
      (me.value?.pending_task_count ?? 0) > 0 ||
      (me.value?.withdrawal_task_count ?? 0) > 0,
  )
  const canAdminister = computed(() => can('core.admin') || can('resources.admin') || can('inventory.admin'))

  /** Load the session once at start-up; a 401 simply means nobody is signed in. */
  async function ensureLoaded(): Promise<void> {
    if (loaded.value) return
    try {
      me.value = await authApi.me()
    } catch {
      me.value = null
    } finally {
      loaded.value = true
    }
  }

  async function refresh(): Promise<void> {
    me.value = await authApi.me()
  }

  async function login(email: string, password: string): Promise<void> {
    me.value = await authApi.login(email, password)
    loaded.value = true
  }

  async function logout(): Promise<void> {
    try {
      await authApi.logout()
    } finally {
      clear()
    }
  }

  function clear(): void {
    me.value = null
    loaded.value = true
  }

  return {
    me,
    loaded,
    isSignedIn,
    isTeamLeader,
    isApprover,
    showApprovals,
    canSeeRequests,
    canAdminister,
    canSeeReports,
    canSeeLoad,
    hasRole,
    can,
    hasScope,
    ensureLoaded,
    refresh,
    login,
    logout,
    clear,
  }
})
