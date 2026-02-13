const DEFAULT_PORT = '8081'

const port = import.meta.env.VITE_API_PORT || DEFAULT_PORT

export const API_BASE = `http://${window.location.hostname}:${port}/api`
export const WS_URL = `ws://${window.location.hostname}:${port}/ws`
