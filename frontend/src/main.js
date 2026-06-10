import './index.css'

import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import { setConfig, frappeRequest, resourcesPlugin } from 'frappe-ui'

import App from './App.vue'
import Wizard from './pages/Wizard.vue'

const router = createRouter({
  history: createWebHistory('/smart-import'),
  routes: [{ path: '/', name: 'Wizard', component: Wizard }],
})

setConfig('resourceFetcher', frappeRequest)

const app = createApp(App)
app.use(resourcesPlugin)
app.use(router)
app.mount('#app')
