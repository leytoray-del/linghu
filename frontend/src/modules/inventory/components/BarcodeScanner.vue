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

defineProps<{ feedback?: { tone: 'ok' | 'warn' | 'bad'; text: string } | null }>()
const emit = defineEmits<{ code: [value: string]; codes: [values: string[]]; close: [] }>()

const video = ref<HTMLVideoElement | null>(null)
const photoInput = ref<HTMLInputElement | null>(null)
const error = ref<string | null>(null)
const starting = ref(true)
const reading = ref(false)
const torchOn = ref(false)
const torchAvailable = ref(false)
const lastRead = ref<string | null>(null)

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
      <p v-else-if="reading" class="state">Reading the photo…</p>
      <p v-else-if="feedback" class="state" :class="feedback.tone" role="status">{{ feedback.text }}</p>
      <p v-else-if="error" class="state bad">{{ error }}</p>
      <p v-else class="state">Point at the barcode. Codes are read automatically.</p>
    </div>
    <p v-if="error && feedback" class="error-line">{{ error }}</p>
    <div class="controls">
      <el-button type="primary" plain :loading="reading" @click="photoInput?.click()">Take a photo of the label</el-button>
      <input ref="photoInput" type="file" accept="image/*" capture="environment" hidden @change="onPhoto" />
      <el-button v-if="torchAvailable" @click="toggleTorch">{{ torchOn ? 'Torch off' : 'Torch on' }}</el-button>
      <span class="spacer" />
      <el-button @click="emit('close')">Stop scanning</el-button>
    </div>
    <p v-if="lastRead" class="muted last">Last read: <span class="mono">{{ lastRead }}</span></p>
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
  inset: 22% 8%;
  border: 2px solid rgba(255, 255, 255, 0.7);
  border-radius: 10px;
}
.state {
  position: absolute;
  inset: auto 10px 10px;
  margin: 0;
  color: #fff;
  font-size: 13.5px;
  font-weight: 500;
  background: rgba(0, 0, 0, 0.6);
  padding: 7px 10px;
  border-radius: 6px;
}
.state.ok {
  background: rgba(23, 120, 74, 0.92);
}
.state.warn {
  background: rgba(163, 92, 0, 0.92);
}
.state.bad {
  background: rgba(179, 38, 30, 0.92);
}
.error-line {
  margin: 0;
  color: var(--erf-bad);
  font-size: 13px;
}
.controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.controls .el-button + .el-button {
  margin-left: 0;
}
.spacer {
  flex: 1;
}
.last {
  margin: 0;
  font-size: 12.5px;
  overflow-wrap: anywhere;
}
</style>
