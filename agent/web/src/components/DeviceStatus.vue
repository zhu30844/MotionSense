<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { fetchStatus, type DeviceStatus } from '@/api'
import { day, duration, megabytes, percent } from '@/format'

const POLL_MS = 2000

const status = ref<DeviceStatus | null>(null)
const error = ref('')
let timer: number | undefined

async function poll() {
  try {
    status.value = await fetchStatus()
    error.value = ''
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

onMounted(() => {
  poll()
  timer = window.setInterval(poll, POLL_MS)
})
onUnmounted(() => window.clearInterval(timer))

const rows = computed<[string, string | number][]>(() => {
  const s = status.value
  if (!s) return []
  return [
    ['Recording', s.frameFlow ? 'frames flowing' : 'no frames'],
    ['System uptime', duration(s.uptimeSeconds)],
    ['Agent uptime', duration(s.agentUptimeSeconds)],
    ['Memory free', `${megabytes(s.memAvailableBytes)} of ${megabytes(s.memTotalBytes)}`],
    ['CPU', percent(s.cpuUsagePercent)],
    ['NPU', percent(s.npuUsagePercent)],
    ['SoC temperature', s.socTempCelsius === null ? '—' : `${s.socTempCelsius.toFixed(1)} °C`],
    ['Viewers', s.clients],
    ['Last day with footage', s.lastRecordingDate === null ? '—' : day(s.lastRecordingDate)],
    ['Version', s.version],
    ['Board clock', new Date(s.time).toLocaleString()],
  ]
})
</script>

<template>
  <section class="card">
    <h2>
      Device status
      <span class="dot" :class="{ ok: status && !error && status.frameFlow }"></span>
    </h2>
    <p v-if="error" class="error">Cannot reach the agent: {{ error }}</p>
    <p v-else-if="!status">Loading…</p>
    <table v-if="status">
      <tbody>
        <tr v-for="[label, value] in rows" :key="label">
          <th>{{ label }}</th>
          <td>{{ value }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.card {
  background: #fff;
  border-radius: 8px;
  padding: 1rem 1.25rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
}
h2 {
  margin: 0 0 0.75rem;
  font-size: 1.1rem;
}
.dot {
  display: inline-block;
  width: 0.6rem;
  height: 0.6rem;
  margin-left: 0.4rem;
  border-radius: 50%;
  background: #c62828;
}
.dot.ok {
  background: #2e7d32;
}
table {
  width: 100%;
  border-collapse: collapse;
}
th,
td {
  padding: 0.35rem 0;
  text-align: left;
  border-top: 1px solid #eceef1;
}
th {
  font-weight: 500;
  color: #5f6670;
}
td {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.error {
  color: #c62828;
}
</style>
