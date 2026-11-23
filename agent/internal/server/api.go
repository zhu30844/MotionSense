package server

import (
	"bufio"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/motionsense/agent/internal/database"
	"github.com/motionsense/agent/internal/recording"
	"github.com/motionsense/agent/internal/stream"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"golang.org/x/sys/unix"
)

// The SoC's only thermal zone. Reads as millidegrees Celsius.
const cpuTempPath = "/sys/class/thermal/thermal_zone0/temp"

// readSocTemp returns the SoC temperature in degrees Celsius, or false if the
// thermal zone cannot be read. A missing sensor is not worth failing the
// whole status response over.
func readSocTemp() (float64, bool) {
	raw, err := os.ReadFile(cpuTempPath)
	if err != nil {
		return 0, false
	}
	milli, err := strconv.Atoi(strings.TrimSpace(string(raw)))
	if err != nil {
		return 0, false
	}
	return float64(milli) / 1000.0, true
}

// lastRecordDate returns the most recent day under dcimRoot that actually
// holds video, as YYYY-MM-DD, or "" if there is none.
//
// Deliberately a filesystem scan rather than a query against VideoMetadata:
// a day row is written when recording starts, and the segment directory is
// created before the first .ts lands in it, so both can name a day that has
// no video in it yet.
func lastRecordDate(dcimRoot string) string {
	days, err := os.ReadDir(dcimRoot)
	if err != nil {
		return ""
	}

	// Skip days dated ahead of today: a boot that starts recording before ntpd
	// corrects the clock writes under whatever date the RTC held, and reporting
	// that as the last recording is misleading.
	today := time.Now().Format("2006-01-02")
	names := make([]string, 0, len(days))
	for _, d := range days {
		if d.IsDir() && recording.ValidDate(d.Name()) && d.Name() <= today {
			names = append(names, d.Name())
		}
	}
	// Names are YYYY-MM-DD, so lexical order is chronological.
	sort.Sort(sort.Reverse(sort.StringSlice(names)))

	for _, name := range names {
		if dayHasVideo(filepath.Join(dcimRoot, name)) {
			return name
		}
	}
	return ""
}

// dayHasVideo reports whether any segment directory under dir holds a .ts.
func dayHasVideo(dir string) bool {
	segments, err := os.ReadDir(dir)
	if err != nil {
		return false
	}
	for _, seg := range segments {
		if !seg.IsDir() {
			continue
		}
		files, err := os.ReadDir(filepath.Join(dir, seg.Name()))
		if err != nil {
			continue
		}
		for _, f := range files {
			if !f.IsDir() && strings.HasSuffix(f.Name(), ".ts") {
				return true
			}
		}
	}
	return false
}

// memAvailable reads MemAvailable from /proc/meminfo, the kernel's own
// estimate of what a new allocation could get. Recording keeps a large page
// cache that sysinfo counts as used but the kernel reclaims on demand.
func memAvailable() (uint64, bool) {
	data, err := os.ReadFile("/proc/meminfo")
	if err != nil {
		return 0, false
	}
	for _, line := range strings.Split(string(data), "\n") {
		if !strings.HasPrefix(line, "MemAvailable:") {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) < 2 {
			return 0, false
		}
		kb, err := strconv.ParseUint(fields[1], 10, 64)
		if err != nil {
			return 0, false
		}
		return kb * 1024, true
	}
	return 0, false
}

// statusResponse : device and app status. Values are raw, with the unit in
// the name; the page formats them. What is unknown is null.
// Version is set at build time, from scripts/version.sh.
var Version = "dev"

type statusResponse struct {
	Version string `json:"version"`
	Clients int    `json:"clients"`
	// True while frames are still arriving from the C daemon over the unix
	// socket. This says the picture is live, not that the device is up: the
	// agent answering this request is what says that. The page cannot infer
	// it from the <img>, which fires no event while a connection is open and
	// silent.
	FrameFlow          bool   `json:"frameFlow"`
	Time               string `json:"time"` // the board's clock, RFC 3339
	UptimeSeconds      int64  `json:"uptimeSeconds"`
	AgentUptimeSeconds int64  `json:"agentUptimeSeconds"`
	MemTotalBytes      uint64 `json:"memTotalBytes"`
	// Memory the kernel would give to a new allocation, from MemAvailable.
	// Not sysinfo's freeram, which excludes reclaimable page cache and so
	// reads as 84% used on a device whose real figure is 20%.
	MemAvailableBytes uint64   `json:"memAvailableBytes"`
	CPUUsagePercent   *float64 `json:"cpuUsagePercent"` // since the previous request
	NPUUsagePercent   *float64 `json:"npuUsagePercent"`
	SocTempCelsius    *float64 `json:"socTempCelsius"`
	LastRecordingDate *string  `json:"lastRecordingDate"` // YYYY-MM-DD

	// The same, as the hand-written pages read them. These go with those pages.
	SystemUptime string  `json:"systemUptime"`
	AppUptime    string  `json:"appUptime"`
	Totalram     uint64  `json:"totalram"`
	Freeram      uint64  `json:"freeram"`
	WorkLoad     float64 `json:"workLoad"`
	CpuTemp      string  `json:"cpuTemp"`
	LastRecord   string  `json:"lastRecord"`
}

// DayRecordingResponse : response body for playback page
type DayRecordingResponse struct {
	Date     string            `json:"date"`
	Segments []SegmentResponse `json:"segments"`
}

// SegmentResponse : playback info for each segment
type SegmentResponse struct {
	Segment      string  `json:"segment"`
	StartTime    string  `json:"startTime"`
	TotalFrames  int64   `json:"totalFrames"`
	PlaylistURL  string  `json:"playlistUrl"`
	MotionFrames []int64 `json:"motionFrames"`
	// Playback length in seconds, summed from the playlist's EXTINF tags.
	// Not derived from TotalFrames: the recorder varies its frame rate with
	// motion, so frames divided by a nominal fps is not the wall-clock length.
	DurationSeconds float64 `json:"durationSeconds"`
	LastWrite       string  `json:"lastWrite"` // TODO: check m3u8 moderation time, should be a string like "2026-05-05"
}

// playlistDuration sums the EXTINF durations in a segment's index.m3u8.
// Returns 0 if the playlist cannot be read or holds no entries.
func playlistDuration(dcimRoot, date, segment string) float64 {
	path, err := recording.MediaFilePath(dcimRoot, date, segment, "index.m3u8")
	if err != nil {
		return 0
	}
	f, err := os.Open(path)
	if err != nil {
		return 0
	}
	defer f.Close()

	var total float64
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := sc.Text()
		if !strings.HasPrefix(line, "#EXTINF:") {
			continue
		}
		v := strings.TrimSuffix(strings.TrimPrefix(line, "#EXTINF:"), ",")
		if d, err := strconv.ParseFloat(strings.TrimSpace(v), 64); err == nil {
			total += d
		}
	}
	if sc.Err() != nil {
		return 0
	}
	return total
}

func mjpegStream(broker *stream.Broker) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", fmt.Sprintf("multipart/x-mixed-replace; boundary=%s", mjpegBoundary))
		w.Header().Set("Cache-Control", "no-cache, no-store")
		w.Header().Set("Connection", "keep-alive")

		flusher, ok := w.(http.Flusher)
		if !ok {
			http.Error(w, "Streaming not supported", http.StatusInternalServerError)
			return
		}
		// Send the headers before waiting for a frame. Without this the
		// handler blocks in the select below and the client sees nothing at
		// all — an <img> then fires neither load nor error and the page sits
		// on "Connecting..." indefinitely when the producer is down.
		w.WriteHeader(http.StatusOK)
		flusher.Flush()

		ch := broker.Subscribe()
		defer broker.Unsubscribe(ch)

		ctx := r.Context()
		for {
			select {
			case <-ctx.Done():
				return
			case frame, ok := <-ch:
				if !ok {
					return
				}
				fmt.Fprintf(w, "--%s\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n",
					mjpegBoundary, len(frame))
				w.Write(frame)
				fmt.Fprintf(w, "\r\n")
				flusher.Flush()
			}
		}
	}
}

func statusHandler(broker *stream.Broker, start time.Time, dcimRoot string) func(http.ResponseWriter, *http.Request) {
	cpu := &cpuMeter{}
	cpu.Usage() // the first reading, for the first request to compare with
	return func(w http.ResponseWriter, r *http.Request) {
		var status statusResponse
		var sysInfo unix.Sysinfo_t
		if err := unix.Sysinfo(&sysInfo); err != nil {
			http.Error(w, "Get System Info failed", http.StatusInternalServerError)
			return
		}
		now := time.Now()
		status.Version = Version
		status.Time = now.Format(time.RFC3339)
		status.Clients = broker.ClientCount()
		// unix.Sysinfo_t's numeric fields are uint64 on 64-bit but uint32 on
		// 32-bit, which is what the RV1106 target is, so convert explicitly.
		status.UptimeSeconds = int64(sysInfo.Uptime)
		status.AgentUptimeSeconds = int64(now.Sub(start).Seconds())
		if v, ok := cpu.Usage(); ok {
			status.CPUUsagePercent = &v
		}
		if v, ok := readNPUUsage(); ok {
			status.NPUUsagePercent = &v
		}

		// Totalram and Freeram are counts of Unit bytes, not bytes. Unit is 1
		// on Linux today, so this changes nothing here, but the field is
		// reported as bytes and should actually be bytes.
		unit := uint64(sysInfo.Unit)
		if unit == 0 {
			unit = 1
		}
		status.MemTotalBytes = uint64(sysInfo.Totalram) * unit
		status.MemAvailableBytes = uint64(sysInfo.Freeram) * unit
		if avail, ok := memAvailable(); ok {
			status.MemAvailableBytes = avail
		}
		if temp, ok := readSocTemp(); ok {
			status.SocTempCelsius = &temp
			status.CpuTemp = fmt.Sprintf("%.1f°C", temp)
		}
		if day := lastRecordDate(dcimRoot); day != "" {
			status.LastRecordingDate = &day
			if t, err := time.Parse("2006-01-02", day); err == nil {
				status.LastRecord = t.Format("2006 Jan 2")
			}
		}

		// Two seconds is comfortably longer than a frame interval at the
		// lowest capture rate this records at.
		if age := broker.SecondsSinceFrame(); age >= 0 && age < 2 {
			status.FrameFlow = true
		}

		status.SystemUptime = (time.Duration(status.UptimeSeconds) * time.Second).String()
		status.AppUptime = now.Sub(start).String()
		status.Totalram = status.MemTotalBytes
		status.Freeram = status.MemAvailableBytes
		// Loads are fixed point with 16 fractional bits; dividing as an
		// integer reported 0 for every load average below 1.00.
		status.WorkLoad = float64(sysInfo.Loads[0]) / 65536.0

		w.Header().Set("Content-Type", "application/json")
		err := json.NewEncoder(w).Encode(status)
		if err != nil {
			log.Printf("json error")
		}
	}
}

func recordingDayHandler(storage *database.Storage, dcimRoot string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		date := r.PathValue("date")
		if !recording.ValidDate(date) {
			http.Error(w, "Invalid date", http.StatusBadRequest)
			return
		}
		segments, err := storage.SegmentsForDay(r.Context(), date)
		// A day that never recorded is an empty day, not a failure. Reply 200
		// with no segments so the client renders "nothing here" rather than
		// having to parse an error body.
		if errors.Is(err, database.ErrNoRecordings) {
			segments = nil
			err = nil
		}
		if err != nil {
			http.Error(w, "Get Segments failed", http.StatusInternalServerError)
			return
		}
		events, err := storage.EventsOfDay(r.Context(), date)
		if errors.Is(err, database.ErrNoRecordings) {
			events = nil
			err = nil
		}
		if err != nil {
			http.Error(w, "Get Events failed", http.StatusInternalServerError)
			return
		}
		eventsByVideoID := make(map[int64][]int64)
		for _, e := range events {
			eventsByVideoID[e.VideoID] = append(eventsByVideoID[e.VideoID], e.MotionFrame)
		}
		response := DayRecordingResponse{
			Date:     date,
			Segments: make([]SegmentResponse, 0, len(segments)),
		}
		for _, segment := range segments {
			response.Segments = append(response.Segments, SegmentResponse{
				Segment:      segment.Folder,
				StartTime:    segment.StartTime,
				TotalFrames:  segment.TotalFrames,
				PlaylistURL:  "/media/" + date + "/" + segment.Folder + "/index.m3u8",
				MotionFrames: eventsByVideoID[segment.ID],

				DurationSeconds: playlistDuration(dcimRoot, date, segment.Folder),
			})
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		err = json.NewEncoder(w).Encode(response)
		if err != nil {
			log.Printf("json error")
		}
	}
}

func recordingsCalendarHandler(storage *database.Storage) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		days, err := storage.ListDays(r.Context())
		if err != nil {
			http.Error(w, "failed to list recording days", http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		err = json.NewEncoder(w).Encode(days)
		if err != nil {
			log.Printf("json error")
		}
	}
}
