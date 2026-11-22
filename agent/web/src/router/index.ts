import { createRouter, createWebHashHistory } from 'vue-router'

import StatusView from '@/views/StatusView.vue'

const router = createRouter({
  // Hash URLs: the agent serves files only and has no fallback to index.html.
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes: [{ path: '/', name: 'status', component: StatusView }],
})

export default router
