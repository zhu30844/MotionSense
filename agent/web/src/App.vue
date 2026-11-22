<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <main>
    <h1>Hello, MotionSense</h1>
    <RouterView />
  </main>
</template>

<style>
body {
  margin: 0;
  font-family: system-ui, sans-serif;
  background: #f4f5f7;
  color: #1c1e21;
}
main {
  max-width: 32rem;
  margin: 3rem auto;
  padding: 0 1rem;
}
</style>
