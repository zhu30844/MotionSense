<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

import { connectLive } from '@/live'

const RETRY_MS = 3000

type State = 'connecting' | 'live' | 'lost'

const video = ref<HTMLVideoElement | null>(null)
const state = ref<State>('connecting')
const error = ref('')
let pc: RTCPeerConnection | undefined
let timer: number | undefined
let unmounted = false

function retry(reason: string) {
  pc?.close()
  pc = undefined
  if (unmounted) return
  state.value = 'lost'
  error.value = reason
  window.clearTimeout(timer)
  timer = window.setTimeout(start, RETRY_MS)
}

async function start() {
  state.value = 'connecting'
  try {
    const conn = await connectLive((stream) => {
      if (video.value) video.value.srcObject = stream
    })
    if (unmounted) return conn.close()
    pc = conn
    conn.addEventListener('connectionstatechange', () => {
      if (conn !== pc) return
      if (conn.connectionState === 'failed' || conn.connectionState === 'closed') {
        retry('connection lost')
      }
    })
  } catch (e) {
    retry(e instanceof Error ? e.message : String(e))
  }
}

// A closed tab unmounts nothing: close here, so the agent frees the place at once.
function leave() {
  window.clearTimeout(timer)
  pc?.close()
  pc = undefined
}
function comeBack(e: PageTransitionEvent) {
  if (e.persisted) start()
}

onMounted(() => {
  window.addEventListener('pagehide', leave)
  window.addEventListener('pageshow', comeBack)
  start()
})
onUnmounted(() => {
  unmounted = true
  window.removeEventListener('pagehide', leave)
  window.removeEventListener('pageshow', comeBack)
  leave()
})
</script>

<template>
  <figure class="live">
    <!-- muted: browsers only autoplay a video that makes no sound -->
    <video ref="video" autoplay muted playsinline @playing="state = 'live'"></video>
    <figcaption v-if="state === 'connecting'">Connecting…</figcaption>
    <figcaption v-else-if="state === 'lost'" class="error">
      No live picture: {{ error }}. Trying again…
    </figcaption>
  </figure>
</template>

<style scoped>
.live {
  margin: 0 0 1rem;
}
video {
  display: block;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: #000;
  border-radius: 8px;
}
figcaption {
  margin-top: 0.4rem;
  color: #5f6670;
}
.error {
  color: #c62828;
}
</style>
