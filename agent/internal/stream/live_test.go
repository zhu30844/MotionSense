package stream

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/pion/webrtc/v4"
)

func offerFrom(t *testing.T, pc *webrtc.PeerConnection) string {
	t.Helper()
	_, err := pc.AddTransceiverFromKind(webrtc.RTPCodecTypeVideo,
		webrtc.RTPTransceiverInit{Direction: webrtc.RTPTransceiverDirectionRecvonly})
	if err != nil {
		t.Fatal(err)
	}
	offer, err := pc.CreateOffer(nil)
	if err != nil {
		t.Fatal(err)
	}
	gathered := webrtc.GatheringCompletePromise(pc)
	if err := pc.SetLocalDescription(offer); err != nil {
		t.Fatal(err)
	}
	<-gathered
	return pc.LocalDescription().SDP
}

func TestLiveSendsFramesToAViewer(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	broker := NewBroker()
	live, err := NewLive()
	if err != nil {
		t.Fatal(err)
	}
	go live.Run(ctx, broker)
	go func() {
		// One IDR NAL unit after an Annex B start code.
		frame := Frame{0, 0, 0, 1, 0x65, 1, 2, 3, 4}
		for ctx.Err() == nil {
			broker.Publish(frame)
			time.Sleep(20 * time.Millisecond)
		}
	}()

	viewer, err := webrtc.NewPeerConnection(webrtc.Configuration{})
	if err != nil {
		t.Fatal(err)
	}
	got := make(chan string, 1)
	viewer.OnTrack(func(track *webrtc.TrackRemote, _ *webrtc.RTPReceiver) {
		if _, _, err := track.ReadRTP(); err == nil {
			got <- track.Codec().MimeType
		}
	})

	answer, err := live.Answer(offerFrom(t, viewer))
	if err != nil {
		t.Fatal(err)
	}
	err = viewer.SetRemoteDescription(webrtc.SessionDescription{Type: webrtc.SDPTypeAnswer, SDP: answer})
	if err != nil {
		t.Fatal(err)
	}

	select {
	case mime := <-got:
		if mime != webrtc.MimeTypeH264 {
			t.Fatalf("viewer got %s, want H264", mime)
		}
	case <-time.After(10 * time.Second):
		t.Fatal("no packet reached the viewer")
	}
	if n := live.Viewers(); n != 1 {
		t.Fatalf("Viewers() = %d with one viewer", n)
	}

	viewer.Close()
	for deadline := time.Now().Add(10 * time.Second); live.Viewers() != 0; {
		if time.Now().After(deadline) {
			t.Fatalf("Viewers() = %d after the viewer closed", live.Viewers())
		}
		time.Sleep(50 * time.Millisecond)
	}
}

func TestLiveRefusesWhatItCannotServe(t *testing.T) {
	live, err := NewLive()
	if err != nil {
		t.Fatal(err)
	}
	if _, err := live.Answer("not sdp"); !errors.Is(err, ErrBadOffer) {
		t.Fatalf("a bad offer gave %v", err)
	}
	if n := live.Viewers(); n != 0 {
		t.Fatalf("Viewers() = %d after a bad offer", n)
	}

	live.viewers.Store(maxViewers)
	if _, err := live.Answer("not sdp"); !errors.Is(err, ErrBusy) {
		t.Fatalf("a full house gave %v", err)
	}
	if n := live.Viewers(); n != maxViewers {
		t.Fatalf("Viewers() = %d after a refusal, want %d", n, maxViewers)
	}
}
