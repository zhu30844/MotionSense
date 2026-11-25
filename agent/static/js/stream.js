// Live picture: H264 over WebRTC, played in the <video>. The same exchange as
// agent/web/src/live.ts, which replaces this page.
class StreamApp {
    constructor() {
        this.video = null;
        this.pc = null;
        this.retryTimer = null;
        this.retryMs = 3000;
    }

    init() {
        if (this.video) return;
        this.video = document.getElementById('streamVideo');
        if (!this.video) return;
        // A closed tab runs nothing else: close so the agent frees the place.
        window.addEventListener('pagehide', () => this.stop());
        window.addEventListener('pageshow', (e) => { if (e.persisted) this.start(); });
        this.start();
    }

    stop() {
        clearTimeout(this.retryTimer);
        if (this.pc) this.pc.close();
        this.pc = null;
    }

    retry() {
        this.stop();
        this.retryTimer = setTimeout(() => this.start(), this.retryMs);
    }

    async start() {
        this.stop();
        // No ICE servers: the browser reaches the board directly.
        const pc = new RTCPeerConnection();
        this.pc = pc;
        try {
            pc.addTransceiver('video', { direction: 'recvonly' });
            pc.addEventListener('track', (e) => {
                this.video.srcObject = e.streams[0] || new MediaStream([e.track]);
            });
            pc.addEventListener('connectionstatechange', () => {
                if (pc !== this.pc) return;
                if (pc.connectionState === 'failed' || pc.connectionState === 'closed') this.retry();
            });

            await pc.setLocalDescription(await pc.createOffer());
            await this.gathered(pc);
            const res = await fetch('/api/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/sdp' },
                body: pc.localDescription.sdp,
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            await pc.setRemoteDescription({ type: 'answer', sdp: await res.text() });
        } catch (e) {
            console.warn('live stream:', e);
            if (pc === this.pc) this.retry();
        }
    }

    // The offer carries the browser's addresses; wait for them, a second at most.
    gathered(pc) {
        return new Promise((resolve) => {
            if (pc.iceGatheringState === 'complete') return resolve();
            const timer = setTimeout(resolve, 1000);
            pc.addEventListener('icegatheringstatechange', () => {
                if (pc.iceGatheringState !== 'complete') return;
                clearTimeout(timer);
                resolve();
            });
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.streamApp = new StreamApp();
    window.streamApp.init();
});
