// Package board reads the board file: what this board has. The daemon reads
// the same file (src/board.c).
package board

import (
	"encoding/json"
	"log"
	"os"
	"path/filepath"
	"syscall"
)

const defaultFile = "/etc/motionsense/board.json"

type Board struct {
	Storage struct {
		Root      string `json:"root"`
		Removable bool   `json:"removable"`
	} `json:"storage"`
}

// Load reads $MS_BOARD_FILE, else the default path. A missing file or key
// leaves the Pro Max value in place.
func Load() Board {
	var b Board
	b.Storage.Root = "/mnt/sdcard"
	b.Storage.Removable = true

	path := os.Getenv("MS_BOARD_FILE")
	if path == "" {
		path = defaultFile
	}
	data, err := os.ReadFile(path)
	if err == nil {
		err = json.Unmarshal(data, &b)
	}
	if err != nil {
		log.Printf("board file: %v, using defaults", err)
	}
	if !filepath.IsAbs(b.Storage.Root) {
		b.Storage.Root = "/mnt/sdcard"
	}
	return b
}

func (b Board) DCIMRoot() string {
	return filepath.Join(b.Storage.Root, "DCIM")
}

// DataDir holds the configuration and the logs.
func (b Board) DataDir() string {
	return filepath.Join(b.Storage.Root, "MotionSense")
}

// StoragePresent is false while removable storage is not mounted: writing
// would land in flash.
func (b Board) StoragePresent() bool {
	if !b.Storage.Removable {
		return true
	}
	var st, parent syscall.Stat_t
	if syscall.Stat(b.Storage.Root, &st) != nil ||
		syscall.Stat(filepath.Dir(b.Storage.Root), &parent) != nil {
		return false
	}
	return st.Dev != parent.Dev
}
