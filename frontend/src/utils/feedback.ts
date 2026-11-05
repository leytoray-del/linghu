import { ElMessage } from 'element-plus'

import { ApiError } from '@/api/http'

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return 'Something went wrong. Try again in a moment.'
}

export function fieldErrors(error: unknown): Record<string, string> {
  return error instanceof ApiError ? error.fields : {}
}

export function showError(error: unknown): void {
  ElMessage({ type: 'error', message: errorMessage(error), duration: 6000, showClose: true })
}

export function showSuccess(message: string): void {
  ElMessage({ type: 'success', message, duration: 4000 })
}
