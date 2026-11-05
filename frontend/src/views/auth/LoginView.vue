<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { errorMessage } from '@/utils/feedback'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const form = reactive({ email: '', password: '' })
const submitting = ref(false)
const error = ref<string | null>(route.query.expired ? 'Your session has ended. Sign in again to continue.' : null)

const showDemo = import.meta.env.VITE_SHOW_DEMO_ACCOUNTS === 'true'
const demoPassword = 'Demo@2026!'
const demoAccounts = [
  { email: 'alex.tan@example.com', who: 'Alex Tan', role: 'Project manager' },
  { email: 'priya.nair@example.com', who: 'Priya Nair', role: 'Team leader, Support' },
  { email: 'daniel.lim@example.com', who: 'Daniel Lim', role: 'Team leader, Development' },
  { email: 'grace.wong@example.com', who: 'Grace Wong', role: 'Director' },
  { email: 'meiling.chua@example.com', who: 'Chua Mei Ling', role: 'Engineer' },
  { email: 'admin@example.com', who: 'Lee Wei Jie', role: 'Administrator' },
]

function useDemo(email: string): void {
  form.email = email
  form.password = demoPassword
}

async function submit(): Promise<void> {
  if (!form.email || !form.password) {
    error.value = 'Enter your email and password.'
    return
  }
  submitting.value = true
  error.value = null
  try {
    await auth.login(form.email.trim(), form.password)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.replace(redirect.startsWith('/') ? redirect : '/')
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login">
    <section class="card">
      <div class="brand">
        <span>Engineering</span>
        <h1>Resource Requests</h1>
        <p class="sub">Plan, request and approve project and SR resources.</p>
      </div>
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="Work email" for="login-email">
          <el-input id="login-email" v-model="form.email" autocomplete="username" type="email" />
        </el-form-item>
        <el-form-item label="Password" for="login-password">
          <el-input id="login-password" v-model="form.password" type="password" autocomplete="current-password" show-password />
        </el-form-item>
        <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="error" />
        <el-button type="primary" native-type="submit" :loading="submitting" class="submit">Sign in</el-button>
      </el-form>
      <p class="hint">Forgot your password? Ask the system administrator to reset it.</p>
    </section>

    <section v-if="showDemo" class="card demo">
      <h2>Demo accounts</h2>
      <p class="hint">
        Every demo account uses the password <code>{{ demoPassword }}</code>. Choose one to fill in the form.
      </p>
      <button v-for="a in demoAccounts" :key="a.email" class="demo-row" type="button" @click="useDemo(a.email)">
        <b>{{ a.who }}</b>
        <span>{{ a.role }}</span>
      </button>
    </section>
  </div>
</template>

<style scoped>
.login {
  min-height: 100%;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: center;
  gap: 20px;
  padding: 10vh 16px 40px;
  background: linear-gradient(180deg, var(--erf-rail) 0 240px, var(--erf-bg) 240px);
}
.card {
  background: var(--erf-surface);
  border: 1px solid var(--erf-line);
  border-radius: 8px;
  padding: 28px;
  width: min(400px, 100%);
  display: flex;
  flex-direction: column;
  gap: 18px;
  box-shadow: 0 10px 30px rgb(15 20 27 / 12%);
}
.brand span {
  font-family: var(--erf-mono);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--erf-muted);
}
.error {
  margin-bottom: 14px;
}
.submit {
  width: 100%;
}
.hint {
  font-size: 12px;
  color: var(--erf-muted);
  margin: 0;
}
.demo {
  width: min(340px, 100%);
  gap: 10px;
}
.demo-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 12px;
  border: 1px solid var(--erf-line);
  border-radius: var(--erf-radius);
  background: var(--erf-surface);
  cursor: pointer;
  font: inherit;
  color: inherit;
  text-align: left;
}
.demo-row:hover {
  border-color: var(--erf-accent);
}
.demo-row span {
  color: var(--erf-muted);
  font-size: 12px;
}
</style>
