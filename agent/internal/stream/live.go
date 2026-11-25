package stream

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"sync/atomic"
	"time"

	"github.com/pion/webrtc/v4"
	"github.com/pion/webrtc/v4/pkg/media"
)

const (
	maxViewers         = 4
	connectTimeout     = 30 * time.Second
	firstFrameDuration = time.Second / 15
)

var (
	ErrBusy     = errors.New("too many viewers")
	ErrBadOffer = errors.New("bad offer")
)

// Live sends the H264 frames to browsers over WebRTC, on one shared track.
type Live struct {
	track   *webrtc.TrackLocalStaticSample
	viewers atomic.Int32
}

func NewLive() (*Live, error) {
	track, err := webrtc.NewTrackLocalStaticSample(
		webrtc.RTPCodecCapability{MimeType: webrtc.MimeTypeH264}, "video", "motionsense")
	if err != nil {
		return nil, err
	}
	return &Live{track: track}, nil
}

// Run writes the broker's frames to the track until ctx ends.
func (l *Live) Run(ctx context.Context, broker *Broker) {
	ch := broker.Subscribe()
	defer broker.Unsubscribe(ch)

	var last time.Time
	for {
		select {
		case <-ctx.Done():
			return
		case frame := <-ch:
			// The socket carries no timestamps: use the gap between frames.
			now := time.Now()
			d := firstFrameDuration
			if !last.IsZero() {
				d = min(now.Sub(last), time.Second)
			}
			last = now
			_ = l.track.WriteSample(media.Sample{Data: frame, Duration: d})
		}
	}
}

// Viewers is the number of browsers connected or connecting.
func (l *Live) Viewers() int {
	return int(l.viewers.Load())
}

// Answer adds a viewer: it takes the browser's SDP offer and returns the answer.
func (l *Live) Answer(offer string) (string, error) {
	if l.viewers.Add(1) > maxViewers {
		l.viewers.Add(-1)
		return "", ErrBusy
	}
	// No ICE servers: the browser reaches the board directly.
	pc, err := webrtc.NewPeerConnection(webrtc.Configuration{})
	if err != nil {
		l.viewers.Add(-1)
		return "", err
	}
	var once sync.Once
	drop := func() {
		once.Do(func() {
			pc.Close()
			l.viewers.Add(-1)
		})
	}

	answer, err := l.negotiate(pc, offer, drop)
	if err != nil {
		drop()
		return "", err
	}
	return answer, nil
}

func (l *Live) negotiate(pc *webrtc.PeerConnection, offer string, drop func()) (string, error) {
	sender, err := pc.AddTrack(l.track)
	if err != nil {
		return "", err
	}
	// pion resends lost packets only while the browser's RTCP is being read.
	go func() {
		buf := make([]byte, 1500)
		for {
			if _, _, err := sender.Read(buf); err != nil {
				return
			}
		}
	}()

	timer := time.AfterFunc(connectTimeout, drop)
	pc.OnConnectionStateChange(func(s webrtc.PeerConnectionState) {
		switch s {
		case webrtc.PeerConnectionStateConnected:
			timer.Stop()
		case webrtc.PeerConnectionStateFailed, webrtc.PeerConnectionStateClosed:
			go drop()
		}
	})

	err = pc.SetRemoteDescription(webrtc.SessionDescription{Type: webrtc.SDPTypeOffer, SDP: offer})
	if err != nil {
		return "", fmt.Errorf("%w: %v", ErrBadOffer, err)
	}
	answer, err := pc.CreateAnswer(nil)
	if err != nil {
		return "", fmt.Errorf("%w: %v", ErrBadOffer, err)
	}
	// The one answer has to carry every address.
	gathered := webrtc.GatheringCompletePromise(pc)
	if err := pc.SetLocalDescription(answer); err != nil {
		return "", err
	}
	<-gathered
	return pc.LocalDescription().SDP, nil
}
