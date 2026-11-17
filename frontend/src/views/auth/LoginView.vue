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
const year = new Date().getFullYear()

async function submit(): Promise<void> {
  if (!form.email || !form.password) {
    error.value = 'Enter your email and password.'
    return
  }
  submitting.value = true
  error.value = null
  try {
    await auth.login(form.email.trim(), form.password)
  } catch (e) {
    error.value = errorMessage(e)
    submitting.value = false
    return
  }
  // Signed in. If the next screen cannot be opened (for example because this tab still runs an older
  // version of the app), load it with a full page load instead of reporting a sign-in failure.
  const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/') ? route.query.redirect : '/'
  try {
    await router.replace(redirect)
  } catch {
    window.location.assign(redirect)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login">
    <aside class="brand-side">
      <div class="brand">
        <svg class="logo" viewBox="0 0 32 32" aria-hidden="true">
          <rect width="32" height="32" rx="7" fill="#26344a" />
          <path d="M8 10h16M8 16h10M8 22h6" stroke="#7aa2f7" stroke-width="3" stroke-linecap="round" />
          <circle cx="23" cy="21" r="4" fill="#4fc48a" />
        </svg>
        <div>
          <span class="org">PSBU Engineering Operations</span>
          <b class="name">OpsHub</b>
        </div>
      </div>

      <div class="pitch">
        <h1>Engineering resources and project equipment, in one place.</h1>
        <ul>
          <li>
            <span class="dot res" />
            <div>
              <b>Resources</b>
              <span>Request engineers for a project, and approve requests from your inbox or email.</span>
            </div>
          </li>
          <li>
            <span class="dot inv" />
            <div>
              <b>Inventory</b>
              <span>Register devices with your phone camera, and track every move to site.</span>
            </div>
          </li>
        </ul>
      </div>

      <span class="foot">© {{ year }} PSBU</span>
    </aside>

    <main class="form-side">
      <section class="card">
        <header>
          <h2>Sign in</h2>
          <p>Use your work email and password.</p>
        </header>
        <el-form label-position="top" @submit.prevent="submit">
          <el-form-item label="Work email" for="login-email">
            <el-input id="login-email" v-model="form.email" autocomplete="username" type="email" size="large" placeholder="name@company.com" />
          </el-form-item>
          <el-form-item label="Password" for="login-password">
            <el-input id="login-password" v-model="form.password" type="password" autocomplete="current-password" show-password size="large" />
          </el-form-item>
          <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="error" />
          <el-button type="primary" native-type="submit" size="large" :loading="submitting" class="submit">Sign in</el-button>
        </el-form>
        <p class="hint">Forgot your password? Ask your system administrator to reset it.</p>
      </section>
    </main>
  </div>
</template>

<style scoped>
.login {
  min-height: 100%;
  display: grid;
  grid-template-columns: minmax(340px, 46%) 1fr;
  background: var(--erf-bg);
}

/* The brand side: dark, with a faint grid and two soft glows in the module colours. */
.brand-side {
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 40px;
  padding: 44px 52px;
  color: #e4e9f0;
  background:
    radial-gradient(520px 380px at 85% 10%, rgb(122 162 247 / 22%), transparent 70%),
    radial-gradient(460px 360px at 10% 95%, rgb(79 196 138 / 16%), transparent 70%),
    linear-gradient(rgb(255 255 255 / 4%) 1px, transparent 1px) 0 0 / 32px 32px,
    linear-gradient(90deg, rgb(255 255 255 / 4%) 1px, transparent 1px) 0 0 / 32px 32px,
    #141c28;
}
.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}
.logo {
  width: 42px;
  height: 42px;
  flex: none;
  filter: drop-shadow(0 6px 16px rgb(0 0 0 / 35%));
}
.org {
  display: block;
  font-family: var(--erf-mono);
  font-size: 11px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #96a2b4;
}
.name {
  display: block;
  font-size: 22px;
  letter-spacing: -0.01em;
}
.pitch h1 {
  font-size: clamp(26px, 2.6vw, 36px);
  line-height: 1.2;
  letter-spacing: -0.015em;
  margin: 0 0 28px;
  max-width: 15em;
  color: #fff;
}
.pitch ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 16px;
  max-width: 30em;
}
.pitch li {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding: 14px 16px;
  border: 1px solid rgb(255 255 255 / 8%);
  border-radius: 10px;
  background: rgb(255 255 255 / 3%);
  backdrop-filter: blur(2px);
}
.pitch li b {
  display: block;
  margin-bottom: 2px;
}
.pitch li span:not(.dot) {
  color: #aab5c5;
  font-size: 14px;
  line-height: 1.5;
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-top: 6px;
  flex: none;
}
.dot.res {
  background: #7aa2f7;
  box-shadow: 0 0 0 4px rgb(122 162 247 / 18%);
}
.dot.inv {
  background: #4fc48a;
  box-shadow: 0 0 0 4px rgb(79 196 138 / 18%);
}
.foot {
  font-size: 12px;
  color: #6f7c8f;
}

/* The form side. */
.form-side {
  position: relative;
  z-index: 1;
  display: grid;
  place-items: center;
  padding: 40px 24px;
}
.card {
  width: min(400px, 100%);
  display: flex;
  flex-direction: column;
  gap: 22px;
  background: var(--erf-surface);
  border: 1px solid var(--erf-line);
  border-radius: 14px;
  padding: 34px 32px 28px;
  box-shadow:
    0 1px 2px rgb(15 20 27 / 6%),
    0 18px 40px rgb(15 20 27 / 10%);
}
.card h2 {
  font-size: 24px;
  letter-spacing: -0.01em;
  margin: 0 0 4px;
}
.card header p {
  margin: 0;
  color: var(--erf-muted);
}
.error {
  margin-bottom: 16px;
}
.submit {
  width: 100%;
  margin-top: 4px;
}
.hint {
  font-size: 13px;
  color: var(--erf-muted);
  margin: 0;
  text-align: center;
}

/* Phones and narrow windows: a compact brand header above the form. */
@media (max-width: 860px) {
  .login {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto 1fr;
  }
  .brand-side {
    padding: max(28px, env(safe-area-inset-top)) 22px 64px;
    gap: 22px;
  }
  .pitch h1 {
    font-size: 22px;
    margin: 0;
  }
  .pitch ul,
  .foot {
    display: none;
  }
  .form-side {
    place-items: start center;
    padding: 0 16px 32px;
    margin-top: -40px;
  }
  .card {
    padding: 26px 22px 22px;
  }
}
</style>
