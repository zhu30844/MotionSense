package server

import (
	"bytes"
	"errors"
	"io"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"time"
)

const (
	updateDir = "/userdata/update"
	// Larger than boot, rootfs and oem can hold together.
	updateMaxBytes = 100 << 20
	// Long enough for the response to reach the browser.
	rebootDelay = 2 * time.Second
	// A stalled upload must not hold the lock for good.
	uploadTimeout = 10 * time.Minute
)

// updateHandler stores an uploaded package and hands it to ms-update, which
// checks it and marks the next boot for recovery. The board then reboots.
func updateHandler() http.HandlerFunc {
	var busy sync.Mutex
	return func(w http.ResponseWriter, r *http.Request) {
		if !busy.TryLock() {
			http.Error(w, "an update is already in progress", http.StatusConflict)
			return
		}
		// Once a package is accepted the lock is kept: the board is about to reboot.
		accepted := false
		defer func() {
			if !accepted {
				busy.Unlock()
			}
		}()

		msUpdate, err := msUpdatePath()
		if err != nil {
			http.Error(w, "updating is not available here", http.StatusNotImplemented)
			return
		}
		// The agent never deletes: ms-update removes an upload it turns down.
		pkg := filepath.Join(updateDir, "incoming.tar")
		if err := storeUpload(w, r, pkg); err != nil {
			if err := exec.Command(msUpdate, "--discard").Run(); err != nil {
				log.Printf("update: discard: %v", err)
			}
			var tooLarge *http.MaxBytesError
			if errors.As(err, &tooLarge) {
				http.Error(w, "package is too large", http.StatusRequestEntityTooLarge)
				return
			}
			if errors.Is(err, os.ErrDeadlineExceeded) {
				http.Error(w, "upload took too long", http.StatusRequestTimeout)
				return
			}
			log.Printf("update: store: %v", err)
			http.Error(w, "could not store the package", http.StatusInternalServerError)
			return
		}

		// ms-update says why on stderr, in words meant for the user.
		var stderr bytes.Buffer
		cmd := exec.Command(msUpdate, "--no-reboot", pkg)
		cmd.Stderr = &stderr
		if err := cmd.Run(); err != nil {
			log.Printf("update: rejected: %s", bytes.TrimSpace(stderr.Bytes()))
			http.Error(w, string(bytes.TrimSpace(stderr.Bytes())), http.StatusUnprocessableEntity)
			return
		}

		accepted = true
		log.Printf("update: package accepted, rebooting into recovery")
		w.WriteHeader(http.StatusAccepted)
		time.AfterFunc(rebootDelay, func() {
			if err := exec.Command("reboot").Run(); err != nil {
				log.Printf("update: reboot: %v", err)
			}
		})
	}
}

// msUpdatePath finds ms-update beside the agent; it is absent in the simulator.
func msUpdatePath() (string, error) {
	self, err := os.Executable()
	if err != nil {
		return "", err
	}
	path := filepath.Join(filepath.Dir(self), "ms-update")
	if _, err := os.Stat(path); err != nil {
		return "", err
	}
	return path, nil
}

func storeUpload(w http.ResponseWriter, r *http.Request, path string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	if err := http.NewResponseController(w).SetReadDeadline(time.Now().Add(uploadTimeout)); err != nil {
		log.Printf("update: no upload deadline: %v", err)
	}
	if _, err := io.Copy(f, http.MaxBytesReader(w, r.Body, updateMaxBytes)); err != nil {
		f.Close()
		return err
	}
	return f.Close()
}
