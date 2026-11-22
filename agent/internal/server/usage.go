package server

import (
	"os"
	"strconv"
	"strings"
	"sync"
	"time"
)

// The load average is no measure of this board: ten idle threads of the
// vendor media stack sleep uninterruptibly and each counts as 1.0.

// cpuMeter turns the counters in /proc/stat into a percentage over the time
// between two readings.
type cpuMeter struct {
	mu        sync.Mutex
	at        time.Time
	busy, all uint64
	percent   float64
	valid     bool
}

// Shorter spans than this are too few ticks to mean anything.
const cpuMinSpan = time.Second

// Usage returns how busy the CPU was since an earlier call, or false until
// there is one to compare with.
func (m *cpuMeter) Usage() (float64, bool) {
	m.mu.Lock()
	defer m.mu.Unlock()

	now := time.Now()
	if !m.at.IsZero() && now.Sub(m.at) < cpuMinSpan {
		return m.percent, m.valid
	}
	busy, all, ok := readCPUTicks()
	if !ok {
		return 0, false
	}
	if !m.at.IsZero() && all > m.all {
		m.percent = 100 * float64(busy-m.busy) / float64(all-m.all)
		m.valid = true
	}
	m.at, m.busy, m.all = now, busy, all
	return m.percent, m.valid
}

// readCPUTicks sums the first line of /proc/stat: user nice system idle
// iowait irq softirq steal. Idle and iowait are the time not busy.
func readCPUTicks() (busy, all uint64, ok bool) {
	raw, err := os.ReadFile("/proc/stat")
	if err != nil {
		return 0, 0, false
	}
	line, _, _ := strings.Cut(string(raw), "\n")
	fields := strings.Fields(line)
	if len(fields) < 5 || fields[0] != "cpu" {
		return 0, 0, false
	}
	for i, f := range fields[1:] {
		if i >= 8 {
			break
		}
		v, err := strconv.ParseUint(f, 10, 64)
		if err != nil {
			return 0, 0, false
		}
		all += v
		if i != 3 && i != 4 {
			busy += v
		}
	}
	return busy, all, true
}

// The rknpu driver reports "NPU load:  7%" here.
const npuLoadPath = "/proc/rknpu/load"

// readNPUUsage returns the NPU load as a percentage, or false on a board
// without the driver.
func readNPUUsage() (float64, bool) {
	raw, err := os.ReadFile(npuLoadPath)
	if err != nil {
		return 0, false
	}
	_, after, found := strings.Cut(string(raw), ":")
	if !found {
		return 0, false
	}
	v, err := strconv.ParseFloat(strings.TrimSuffix(strings.TrimSpace(after), "%"), 64)
	if err != nil {
		return 0, false
	}
	return v, true
}
