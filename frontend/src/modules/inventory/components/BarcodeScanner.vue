<script setup lang="ts">
/**
 * Reads barcodes with the device camera. Uses the browser's own barcode reader where it exists
 * (Chrome on Android) and the ZXing library elsewhere (for example Safari on iPhone).
 * Emits each distinct code once; the parent decides which code is the serial number.
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = withDefaults(defineProps<{ continuous?: boolean }>(), { continuous: true })
const emit = defineEmits<{ code: [value: string]; close: [] }>()

const video = ref<HTMLVideoElement | null>(null)
const error = ref<string | null>(null)
const starting = ref(true)
const torchOn = ref(false)
const torchAvailable = ref(false)

let stream: MediaStream | null = null
let timer: number | undefined
let stopZxing: (() => void) | null = null
const recent = new Map<string, number>()

interface DetectorLike {
  detect(source: HTMLVideoElement): Promise<{ rawValue: string }[]>
}

function found(raw: string): void {
  const value = raw.trim()
  if (!value) return
  const now = Date.now()
  // The same code stays in view for a while; report it again only after a pause.
  if ((recent.get(value) ?? 0) > now - 2500) return
  recent.set(value, now)
  try {
    navigator.vibrate?.(60)
  } catch {
    /* vibration is optional */
  }
  emit('code', value)
  if (!props.continuous) emit('close')
}

async function start(): Promise<void> {
  if (!navigator.mediaDevices?.getUserMedia) {
    error.value = 'This browser cannot use the camera. Type the serial number instead.'
    starting.value = false
    return
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    })
  } catch {
    error.value = 'The camera could not be opened. Allow camera access for this site, or type the serial number instead.'
    starting.value = false
    return
  }
  const track = stream.getVideoTracks()[0]
  const caps = (track?.getCapabilities?.() ?? {}) as { torch?: boolean }
  torchAvailable.value = !!caps.torch
  if (!video.value) return
  video.value.srcObject = stream
  await video.value.play().catch(() => {})
  starting.value = false

  const Native = (window as unknown as { BarcodeDetector?: new (o: { formats: string[] }) => DetectorLike }).BarcodeDetector
  if (Native) {
    const detector = new Native({ formats: ['code_128', 'code_39', 'ean_13', 'ean_8', 'upc_a', 'qr_code', 'data_matrix'] })
    timer = window.setInterval(async () => {
      if (!video.value || video.value.readyState < 2) return
      try {
        for (const code of await detector.detect(video.value)) found(code.rawValue)
      } catch {
        /* a frame that cannot be read is skipped */
      }
    }, 250)
    return
  }
  const { BrowserMultiFormatReader } = await import('@zxing/browser')
  const reader = new BrowserMultiFormatReader()
  const controls = await reader.decodeFromVideoElement(video.value, (result) => {
    if (result) found(result.getText())
  })
  stopZxing = () => controls.stop()
}

async function toggleTorch(): Promise<void> {
  const track = stream?.getVideoTracks()[0]
  if (!track) return
  try {
    await track.applyConstraints({ advanced: [{ torch: !torchOn.value } as MediaTrackConstraintSet] })
    torchOn.value = !torchOn.value
  } catch {
    torchAvailable.value = false
  }
}

function stop(): void {
  window.clearInterval(timer)
  stopZxing?.()
  stream?.getTracks().forEach((t) => t.stop())
  stream = null
}

onMounted(start)
onBeforeUnmount(stop)
</script>

<template>
  <div class="scanner">
    <div class="viewport">
      <video ref="video" muted playsinline aria-label="Camera view for scanning barcodes" />
      <div class="reticle" aria-hidden="true" />
      <p v-if="starting" class="state">Opening the camera…</p>
      <p v-if="error" class="state error">{{ error }}</p>
    </div>
    <div class="controls">
      <span class="muted">Point the camera at the barcode label.</span>
      <span class="spacer" />
      <el-button v-if="torchAvailable" size="small" @click="toggleTorch">{{ torchOn ? 'Torch off' : 'Torch on' }}</el-button>
      <el-button size="small" @click="emit('close')">Stop scanning</el-button>
    </div>
  </div>
</template>

<style scoped>
.scanner {
  display: grid;
  gap: 8px;
}
.viewport {
  position: relative;
  background: #0b0f15;
  border-radius: var(--erf-radius);
  overflow: hidden;
  aspect-ratio: 4 / 3;
  max-height: 46vh;
  width: 100%;
}
video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.reticle {
  position: absolute;
  inset: 22% 10%;
  border: 2px solid rgba(255, 255, 255, 0.7);
  border-radius: 10px;
  box-shadow: 0 0 0 999px rgba(0, 0, 0, 0.25);
}
.state {
  position: absolute;
  inset: auto 12px 12px;
  margin: 0;
  color: #fff;
  font-size: 13px;
  background: rgba(0, 0, 0, 0.55);
  padding: 6px 10px;
  border-radius: 6px;
}
.state.error {
  background: rgba(179, 38, 30, 0.85);
}
.controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.spacer {
  flex: 1;
}
</style>
