/** How long to wait for the browser's own addresses before sending the offer. */
const GATHER_MS = 1000

function gathered(pc: RTCPeerConnection): Promise<void> {
  return new Promise((resolve) => {
    if (pc.iceGatheringState === 'complete') return resolve()
    const timer = window.setTimeout(resolve, GATHER_MS)
    pc.addEventListener('icegatheringstatechange', () => {
      if (pc.iceGatheringState !== 'complete') return
      window.clearTimeout(timer)
      resolve()
    })
  })
}

/**
 * Starts the live picture: offers to POST /api/stream and hands the video
 * that arrives to onStream. Close the connection that is returned to stop.
 */
export async function connectLive(
  onStream: (stream: MediaStream) => void,
): Promise<RTCPeerConnection> {
  // No ICE servers: the browser reaches the board directly.
  const pc = new RTCPeerConnection()
  try {
    pc.addTransceiver('video', { direction: 'recvonly' })
    pc.addEventListener('track', (e) => onStream(e.streams[0] ?? new MediaStream([e.track])))

    await pc.setLocalDescription(await pc.createOffer())
    await gathered(pc)

    const res = await fetch('/api/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/sdp' },
      body: pc.localDescription?.sdp,
    })
    if (res.status === 503) throw new Error('too many viewers')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    await pc.setRemoteDescription({ type: 'answer', sdp: await res.text() })
    return pc
  } catch (e) {
    pc.close()
    throw e
  }
}
