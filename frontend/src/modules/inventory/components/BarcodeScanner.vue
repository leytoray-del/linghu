<script setup lang="ts">
/**
 * Reads barcodes with the device camera, live or from a photo.
 *
 * Live: the browser's own reader where it exists (Chrome on Android), otherwise ZXing (iPhone).
 * Photo: the phone takes a full-resolution picture of the label, which reads small or dense barcodes
 * far more reliably than live video, and every barcode on the label is read from it.
 * Each distinct code is emitted; the parent decides which one is the serial number and reports the
 * outcome back through `feedback`, which is shown on the camera view.
 */
import { BarcodeFormat, DecodeHintType } from '@zxing/library'
import { onBeforeUnmount, onMounted, ref } from 'vue'

defineProps<{
  /** The outcome of the last read. Give a new `key` for every new outcome so it flashes, even with the same text. */
  feedback?: { tone: 'ok' | 'warn' | 'bad'; text: string; action?: string; key?: number } | null
  /** Shown at the top of the camera view, for example the model being scanned. */
  caption?: string
}>()
const emit = defineEmits<{ code: [value: string]; codes: [values: string[]]; action: []; close: [] }>()

const video = ref<HTMLVideoElement | null>(null)
const photoInput = ref<HTMLInputElement | null>(null)
const error = ref<string | null>(null)
const starting = ref(true)
const reading = ref(false)
const torchOn = ref(false)
const torchAvailable = ref(false)
const lastRead = ref<string | null>(null)
/** True after a while without reading anything, to suggest the photo instead. */
const quiet = ref(false)
let lastReadAt = Date.now()
let quietTimer: number | undefined

let stream: MediaStream | null = null
let timer: number | undefined
const recent = new Map<string, number>()

const FORMATS = [
  BarcodeFormat.CODE_128,
  BarcodeFormat.CODE_39,
  BarcodeFormat.CODE_93,
  BarcodeFormat.EAN_13,
  BarcodeFormat.EAN_8,
  BarcodeFormat.UPC_A,
  BarcodeFormat.ITF,
  BarcodeFormat.QR_CODE,
  BarcodeFormat.DATA_MATRIX,
]

function hints(): Map<DecodeHintType, unknown> {
  const h = new Map<DecodeHintType, unknown>()
  h.set(DecodeHintType.POSSIBLE_FORMATS, FORMATS)
  h.set(DecodeHintType.TRY_HARDER, true)
  return h
}

interface DetectorLike {
  detect(source: CanvasImageSource): Promise<{ rawValue: string }[]>
}

function found(raw: string): void {
  const value = raw.trim()
  if (!value) return
  lastRead.value = value
  lastReadAt = Date.now()
  quiet.value = false
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
}

async function start(): Promise<void> {
  if (!navigator.mediaDevices?.getUserMedia) {
    error.value = 'This browser cannot show the camera here. Use "Take a photo of the label" instead.'
    starting.value = false
    return
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } },
      audio: false,
    })
  } catch {
    error.value = 'The camera could not be opened. Allow camera access for this site, or use "Take a photo of the label".'
    starting.value = false
    return
  }
  const track = stream.getVideoTracks()[0]
  const caps = (track?.getCapabilities?.() ?? {}) as { torch?: boolean; focusMode?: string[] }
  torchAvailable.value = !!caps.torch
  if (caps.focusMode?.includes('continuous')) {
    track?.applyConstraints({ advanced: [{ focusMode: 'continuous' } as MediaTrackConstraintSet] }).catch(() => {})
  }
  if (!video.value) return
  video.value.srcObject = stream
  await video.value.play().catch(() => {})
  starting.value = false

  const Native = (window as unknown as { BarcodeDetector?: new (o: { formats: string[] }) => DetectorLike }).BarcodeDetector
  if (Native) {
    const detector = new Native({ formats: ['code_128', 'code_39', 'code_93', 'ean_13', 'ean_8', 'upc_a', 'itf', 'qr_code', 'data_matrix'] })
    timer = window.setInterval(async () => {
      if (!video.value || video.value.readyState < 2) return
      try {
        for (const code of await detector.detect(video.value)) found(code.rawValue)
      } catch {
        /* a frame that cannot be read is skipped */
      }
    }, 200)
    return
  }
  // ZXing reads one barcode per image and struggles when a frame holds several barcodes and text, so
  // each frame is read in parts: the area inside the guide, then overlapping horizontal bands of it.
  const { BrowserMultiFormatReader } = await import('@zxing/browser')
  const reader = new BrowserMultiFormatReader(hints())
  const frame = document.createElement('canvas')
  let busy = false
  let turn = 0
  timer = window.setInterval(() => {
    const v = video.value
    if (busy || !v || v.readyState < 2 || !v.videoWidth) return
    busy = true
    try {
      const scale = Math.min(1, 1280 / v.videoWidth)
      frame.width = Math.round(v.videoWidth * scale)
      frame.height = Math.round(v.videoHeight * scale)
      frame.getContext('2d', { willReadFrequently: true })!.drawImage(v, 0, 0, frame.width, frame.height)
      // The guide covers the middle of the view; read a little more than it.
      const gx = Math.round(frame.width * 0.04)
      const gy = Math.round(frame.height * 0.15)
      const guide = canvasFrom(frame, gx, gy, frame.width - 2 * gx, frame.height - 2 * gy)
      // Spread the work over frames. Enlarged passes read small or dense barcodes, whose bars are only
      // one or two pixels wide in a video frame.
      const [parts, zoom] = PASSES[turn++ % PASSES.length]!
      for (const text of readRegions(reader, guide, parts, zoom)) found(text)
    } finally {
      busy = false
    }
  }, 180)
}

/** Live passes as [bands, enlargement]: 0 bands reads the whole area at once. */
const PASSES: [number, number][] = [
  [0, 1],
  [3, 1],
  [0, 2],
  [3, 2],
  [5, 2],
]

/** Read the canvas whole (parts = 0) or in overlapping horizontal bands, optionally enlarged. */
function readRegions(
  reader: { decodeFromCanvas(c: HTMLCanvasElement): { getText(): string } },
  c: HTMLCanvasElement,
  parts: number,
  zoom = 1,
): string[] {
  const out: string[] = []
  const tryRead = (x: HTMLCanvasElement) => {
    try {
      out.push(reader.decodeFromCanvas(x).getText().trim())
    } catch {
      /* no barcode here */
    }
  }
  if (!parts) {
    tryRead(zoom === 1 ? c : canvasFrom(c, 0, 0, c.width, c.height, false, zoom))
    return out
  }
  const band = Math.round((c.height / parts) * 1.6)
  const step = Math.max(1, Math.round(c.height / parts))
  for (let y = 0; y < c.height; y += step) tryRead(canvasFrom(c, 0, y, c.width, Math.min(band, c.height - y), false, zoom))
  return out
}

// ---- reading every barcode in a photo ----

function loadImage(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('The photo could not be opened.'))
    img.src = URL.createObjectURL(file)
  })
}

/** Copy part of an image to a new canvas, optionally turned by 90 degrees and enlarged. */
function canvasFrom(
  source: CanvasImageSource,
  sx: number,
  sy: number,
  sw: number,
  sh: number,
  rotate = false,
  zoom = 1,
): HTMLCanvasElement {
  const c = document.createElement('canvas')
  const w = Math.round(sw * zoom)
  const h = Math.round(sh * zoom)
  c.width = rotate ? h : w
  c.height = rotate ? w : h
  const g = c.getContext('2d', { willReadFrequently: true })!
  g.imageSmoothingQuality = 'high'
  if (rotate) {
    g.translate(c.width / 2, c.height / 2)
    g.rotate(Math.PI / 2)
    g.drawImage(source, sx, sy, sw, sh, -w / 2, -h / 2, w, h)
  } else {
    g.drawImage(source, sx, sy, sw, sh, 0, 0, w, h)
  }
  return c
}

async function readPhoto(file: File): Promise<string[]> {
  const img = await loadImage(file)
  const scale = Math.min(1, 2000 / Math.max(img.naturalWidth, img.naturalHeight))
  const base = canvasFrom(img, 0, 0, img.naturalWidth, img.naturalHeight)
  const W = base.width
  const H = base.height
  const work = document.createElement('canvas')
  work.width = Math.round(W * scale)
  work.height = Math.round(H * scale)
  work.getContext('2d')!.drawImage(base, 0, 0, work.width, work.height)
  URL.revokeObjectURL(img.src)

  const codes = new Set<string>()
  const Native = (window as unknown as { BarcodeDetector?: new (o: { formats: string[] }) => DetectorLike }).BarcodeDetector
  if (Native) {
    try {
      const d = new Native({ formats: ['code_128', 'code_39', 'code_93', 'ean_13', 'ean_8', 'upc_a', 'itf', 'qr_code', 'data_matrix'] })
      for (const r of await d.detect(work)) codes.add(r.rawValue.trim())
    } catch {
      /* fall back to ZXing below */
    }
    if (codes.size) return [...codes]
  }
  const { BrowserMultiFormatReader } = await import('@zxing/browser')
  const reader = new BrowserMultiFormatReader(hints())
  // Read the whole photo, then overlapping horizontal bands, which separates barcodes stacked on a label.
  // Repeat turned by 90 degrees for labels photographed sideways.
  for (const rotate of [false, true]) {
    const full = canvasFrom(work, 0, 0, work.width, work.height, rotate)
    // Normal size first; enlarge only when nothing was found, which keeps easy labels quick.
    for (const zoom of [1, 2]) {
      for (const parts of [0, 3, 5, 8]) {
        readRegions(reader, full, parts, zoom).forEach((t) => codes.add(t))
        await new Promise((r) => setTimeout(r, 0)) // keep the page responsive
      }
      if (codes.size) break
    }
    if (codes.size) break
  }
  return [...codes]
}

async function onPhoto(event: Event): Promise<void> {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (photoInput.value) photoInput.value.value = ''
  if (!file) return
  reading.value = true
  error.value = null
  try {
    const codes = await readPhoto(file)
    if (!codes.length) {
      error.value = 'No barcode could be read from the photo. Hold the phone closer, keep the label flat and in focus, and try again.'
    } else {
      lastRead.value = codes.join(', ')
      emit('codes', codes)
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'The photo could not be read.'
  } finally {
    reading.value = false
  }
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
  window.clearInterval(quietTimer)
  stream?.getTracks().forEach((t) => t.stop())
  stream = null
}

onMounted(() => {
  start()
  quietTimer = window.setInterval(() => (quiet.value = Date.now() - lastReadAt > 7000), 1000)
})
onBeforeUnmount(stop)
</script>

<template>
  <div class="scanner">
    <div class="viewport">
      <video ref="video" muted playsinline aria-label="Camera view for scanning barcodes" />
      <div class="reticle" aria-hidden="true" />
      <div class="top">
        <p class="caption">{{ caption }}</p>
        <div class="icons">
          <button v-if="torchAvailable" type="button" class="icon" :class="{ on: torchOn }" :aria-label="torchOn ? 'Torch off' : 'Torch on'" :aria-pressed="torchOn" @click="toggleTorch">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 2h6l-1 6h3l-7 14 1-9H7z" /></svg>
          </button>
          <button type="button" class="icon" aria-label="Take a photo of the label" :disabled="reading" @click="photoInput?.click()">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h3l2-3h6l2 3h3a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1z" /><circle cx="12" cy="13" r="4" /></svg>
          </button>
          <button type="button" class="icon" aria-label="Stop scanning" @click="emit('close')">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>
      </div>
      <input ref="photoInput" type="file" accept="image/*" capture="environment" hidden @change="onPhoto" />
      <p v-if="starting" class="state">Opening the camera…</p>
      <p v-else-if="reading" class="state">Reading the photo…</p>
      <div v-else-if="feedback" :key="feedback.key ?? feedback.text" class="state pop" :class="feedback.tone" role="status">
        <p>{{ feedback.text }}</p>
        <button v-if="feedback.action" type="button" class="state-action" @click="emit('action')">{{ feedback.action }}</button>
      </div>
      <p v-else-if="error" class="state bad">{{ error }}</p>
      <p v-else-if="quiet" class="state">Hard to read? Tap the camera button at the top to take a photo of the label instead.</p>
      <p v-else class="state">Point at the barcode. It is read automatically.</p>
    </div>
    <p v-if="error && feedback" class="error-line">{{ error }}</p>
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
  border-radius: 12px;
  overflow: hidden;
  aspect-ratio: 4 / 3;
  max-height: 52vh;
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
  inset: 16% 4% 26%;
  border: 2px solid rgba(255, 255, 255, 0.75);
  border-radius: 10px;
}
.top {
  position: absolute;
  inset: 8px 8px auto;
  display: flex;
  align-items: center;
  gap: 8px;
}
.caption {
  flex: 1;
  min-width: 0;
  margin: 0;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.8);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.icons {
  display: flex;
  gap: 8px;
}
.icon {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  cursor: pointer;
}
.icon svg {
  width: 22px;
  height: 22px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.icon.on {
  background: #f5c542;
  color: #1b2533;
}
.icon:disabled {
  opacity: 0.5;
}
.icon:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 2px;
}
.state {
  position: absolute;
  inset: auto 8px 8px;
  margin: 0;
  color: #fff;
  font-size: 15px;
  font-weight: 500;
  line-height: 1.4;
  background: rgba(0, 0, 0, 0.62);
  padding: 10px 12px;
  border-radius: 10px;
}
.state p {
  margin: 0;
}
.state.ok,
.state.warn,
.state.bad {
  font-size: 17px;
  font-weight: 600;
  padding: 12px 14px;
}
.state.ok {
  background: rgba(23, 120, 74, 0.95);
}
.state.warn {
  background: rgba(163, 92, 0, 0.95);
}
.state.bad {
  background: rgba(179, 38, 30, 0.95);
}
.pop {
  animation: pop 0.35s ease-out;
}
@keyframes pop {
  0% {
    transform: scale(0.94);
    opacity: 0.4;
  }
  100% {
    transform: scale(1);
    opacity: 1;
  }
}
@media (prefers-reduced-motion: reduce) {
  .pop {
    animation: none;
  }
}
.state-action {
  margin-top: 8px;
  font: inherit;
  font-size: 15px;
  font-weight: 600;
  color: #1b2533;
  background: #fff;
  border: 0;
  border-radius: 8px;
  padding: 8px 12px;
  cursor: pointer;
}
.error-line {
  margin: 0;
  color: var(--erf-bad);
  font-size: 13px;
}
</style>
