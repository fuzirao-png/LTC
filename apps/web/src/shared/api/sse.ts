export function openJobEvents(jobId: string, onMessage: (event: MessageEvent<string>) => void): EventSource {
  const source = new EventSource(`/api/v1/jobs/${encodeURIComponent(jobId)}/events`, { withCredentials: true })
  source.onmessage = onMessage
  return source
}
