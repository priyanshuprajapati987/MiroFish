import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import i18n from './i18n'

const app = createApp(App)

app.use(router)
app.use(i18n)

app.config.errorHandler = (err, instance, info) => {
  console.error('Global error:', err, info)
}

window.addEventListener('unhandledrejection', (event) => {
  console.error('Unhandled promise rejection:', event.reason)
})

app.mount('#app')
