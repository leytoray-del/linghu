import { onBeforeUnmount, ref } from 'vue'

const QUERY = '(max-width: 860px)'

/** Whether the phone layout is in use. Updates when the window is resized or the phone is turned. */
export function useMobile() {
  const media = window.matchMedia(QUERY)
  const isMobile = ref(media.matches)
  const update = () => (isMobile.value = media.matches)
  media.addEventListener('change', update)
  onBeforeUnmount(() => media.removeEventListener('change', update))
  return { isMobile }
}

/** Whether the system runs as an installed app (opened from the home screen, without the browser bar). */
export function isInstalledApp(): boolean {
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    (navigator as unknown as { standalone?: boolean }).standalone === true
  )
}
