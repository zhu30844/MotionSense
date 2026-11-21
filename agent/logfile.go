package main

import (
	"bytes"
	"context"
	"log"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/motionsense/agent/internal/board"
)

const earlyLogMax = 64 << 10

// storageLog writes to stderr, and to a file on storage once there is one.
// What is logged before that is kept and written first.
type storageLog struct {
	mu    sync.Mutex
	early bytes.Buffer
	file  *os.File
}

func (l *storageLog) Write(p []byte) (int, error) {
	l.mu.Lock()
	defer l.mu.Unlock()
	os.Stderr.Write(p)
	if l.file != nil {
		return l.file.Write(p)
	}
	if l.early.Len() < earlyLogMax {
		l.early.Write(p)
	}
	return len(p), nil
}

func (l *storageLog) attach(f *os.File) {
	l.mu.Lock()
	defer l.mu.Unlock()
	f.Write(l.early.Bytes())
	l.early = bytes.Buffer{}
	l.file = f
}

// logToStorage sends the log to agent.log as soon as storage is there.
func logToStorage(ctx context.Context, b board.Board) {
	l := &storageLog{}
	log.SetOutput(l)
	go func() {
		for {
			if b.StoragePresent() && os.MkdirAll(b.DataDir(), 0o755) == nil {
				f, err := os.OpenFile(filepath.Join(b.DataDir(), "agent.log"),
					os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
				if err == nil {
					l.attach(f)
					return
				}
			}
			select {
			case <-ctx.Done():
				return
			case <-time.After(time.Second):
			}
		}
	}()
}
