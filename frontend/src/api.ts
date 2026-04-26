import { useEffect, useState } from 'react'

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

type ApiState<T> = {
  data: T | null
  loading: boolean
  error: string | null
}

type StoredApiState<T> = {
  key: string
  data: T | null
  error: string | null
}

export async function fetchApi<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal })
  if (!response.ok) {
    const message = await readErrorMessage(response)
    throw new Error(message || `HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}

export function useApi<T>(path: string | null, refreshKey = 0): ApiState<T> {
  const requestKey = path ? `${path}::${refreshKey}` : ''
  const [state, setState] = useState<StoredApiState<T>>({
    key: '',
    data: null,
    error: null,
  })

  useEffect(() => {
    if (!path) {
      return
    }

    const controller = new AbortController()

    fetchApi<T>(path, controller.signal)
      .then((data) => {
        setState({ key: requestKey, data, error: null })
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return
        }
        setState({
          key: requestKey,
          data: null,
          error: error instanceof Error ? error.message : '请求失败',
        })
      })

    return () => controller.abort()
  }, [path, requestKey])

  if (!path) {
    return { data: null, loading: false, error: null }
  }
  if (state.key !== requestKey) {
    return { data: null, loading: true, error: null }
  }
  return { data: state.data, loading: false, error: state.error }
}

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string }
    return payload.detail ?? response.statusText
  } catch {
    return response.statusText
  }
}
