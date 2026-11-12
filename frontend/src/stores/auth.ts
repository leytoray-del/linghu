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

  const isTeamLeader = computed(() => (me.value?.led_team_ids.length ?? 0) > 0)
  const canSeeReports = computed(() => isTeamLeader.value || hasRole('DIRECTOR', 'ADMIN', 'VIEWER'))
  const canSeeLoad = computed(() => isTeamLeader.value || hasRole('DIRECTOR', 'ADMIN', 'VIEWER'))
  const isApprover = computed(() => isTeamLeader.value || hasRole('DIRECTOR'))

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
