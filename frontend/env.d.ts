/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Show the demo account list on the sign-in page. */
  readonly VITE_SHOW_DEMO_ACCOUNTS?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
