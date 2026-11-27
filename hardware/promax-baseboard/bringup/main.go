// Bringup tests a freshly assembled Pro Max baseboard from the board itself.
//
//	GOOS=linux GOARCH=arm GOARM=7 CGO_ENABLED=0 go build -o bringup .
//	./bringup              every test that moves nothing: i2c oled vin leds buttons sd
//	./bringup servo        sweeps both servos; keep the head clear
//	./bringup i2c vin      only the tests named
//
// It needs a kernel whose device tree enables what the baseboard uses: i2c1 and i2c3 (their m1
// pins only), pwm10 and pwm11 (m1 pins only), and sdio on sdmmc1m0. A test that finds its device
// missing says which one. Nothing here writes to the SD card or to the EEPROM.
package main

import (
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"
)

var (
	boardBus = flag.Int("i2c-board", 3, "I2C bus of the RTC, the EEPROM and the sensor")
	headBus  = flag.Int("i2c-head", 1, "I2C bus of the OLED")
	wait     = flag.Duration("wait", 10*time.Second, "how long to wait for a button")
)

// GPIO numbers are bank*32 + group*8 + pin, as on Luckfox's pinout picture.
const (
	gpioLedNet  = 48 // GPIO1_C0, header pin 12
	gpioLedRec  = 49 // GPIO1_C1, pin 14
	gpioRtcInt  = 51 // GPIO1_C3, pin 16
	gpioBtnNet  = 52 // GPIO1_C4, pin 7
	gpioBtnStop = 53 // GPIO1_C5, pin 6
	gpioCardDet = 70 // GPIO2_A6, pin 29
)

// Where the SoC has the controllers the baseboard uses; sysfs names them by address.
const (
	addrPwmPan  = "ff490020" // pwm10, pin 5
	addrPwmTilt = "ff490030" // pwm11, pin 4
	addrSdio    = "ff9a0000"
)

var failed int

func pass(format string, a ...any) { fmt.Printf("  ok    "+format+"\n", a...) }
func note(format string, a ...any) { fmt.Printf("        "+format+"\n", a...) }
func fail(format string, a ...any) {
	failed++
	fmt.Printf("  FAIL  "+format+"\n", a...)
}

// ---- I2C ----

type i2c struct{ f *os.File }

func openI2C(bus int, addr uint8) (*i2c, error) {
	f, err := os.OpenFile(fmt.Sprintf("/dev/i2c-%d", bus), os.O_RDWR, 0)
	if err != nil {
		return nil, err
	}
	// I2C_SLAVE_FORCE: the kernel's own RTC driver may hold the address.
	if _, _, e := syscall.Syscall(syscall.SYS_IOCTL, f.Fd(), 0x0706, uintptr(addr)); e != 0 {
		f.Close()
		return nil, e
	}
	return &i2c{f}, nil
}

func (d *i2c) regs(reg uint8, n int) ([]byte, error) {
	if _, err := d.f.Write([]byte{reg}); err != nil {
		return nil, err
	}
	buf := make([]byte, n)
	_, err := d.f.Read(buf)
	return buf, err
}

func bcd(b byte) int { return int(b>>4)*10 + int(b&0x0f) }

func crc8(data []byte) byte {
	crc := byte(0xff)
	for _, b := range data {
		crc ^= b
		for i := 0; i < 8; i++ {
			if crc&0x80 != 0 {
				crc = crc<<1 ^ 0x31
			} else {
				crc <<= 1
			}
		}
	}
	return crc
}

func testI2C() {
	fmt.Printf("i2c: bus %d\n", *boardBus)
	if _, err := os.Stat(fmt.Sprintf("/dev/i2c-%d", *boardBus)); err != nil {
		fail("no /dev/i2c-%d: enable i2c%d with its m1 pins in the device tree", *boardBus, *boardBus)
		return
	}
	if d, err := openI2C(*boardBus, 0x68); err != nil {
		fail("DS3231 at 0x68: %v", err)
	} else {
		defer d.f.Close()
		if r, err := d.regs(0x00, 0x13); err != nil {
			fail("DS3231 at 0x68 does not answer: %v", err)
		} else {
			temp := float64(int8(r[0x11])) + float64(r[0x12]>>6)*0.25
			pass("DS3231: 20%02d-%02d-%02d %02d:%02d:%02d, %.2f C inside the chip", bcd(r[6]), bcd(r[5]&0x1f), bcd(r[4]),
				bcd(r[2]&0x3f), bcd(r[1]), bcd(r[0]), temp)
			if r[0x0f]&0x80 != 0 {
				note("its oscillator has stopped at some time (no coin cell yet?): the time above is not valid")
			}
		}
	}
	if d, err := openI2C(*boardBus, 0x50); err != nil {
		fail("24AA02E48 at 0x50: %v", err)
	} else {
		defer d.f.Close()
		if r, err := d.regs(0xfa, 6); err != nil {
			fail("24AA02E48 at 0x50 does not answer: %v", err)
		} else if r[0] == 0xff && r[1] == 0xff && r[2] == 0xff {
			fail("24AA02E48 answers but holds no address: % x", r)
		} else {
			pass("24AA02E48: address %02x:%02x:%02x:%02x:%02x:%02x", r[0], r[1], r[2], r[3], r[4], r[5])
		}
	}
	if d, err := openI2C(*boardBus, 0x44); err != nil {
		fail("SHT40 at 0x44: %v", err)
	} else {
		defer d.f.Close()
		sht40(d)
	}
}

func sht40(d *i2c) {
	buf := make([]byte, 6)
	if _, err := d.f.Write([]byte{0xfd}); err != nil { // measure, high precision
		fail("SHT40 at 0x44 does not answer: %v", err)
		return
	}
	time.Sleep(15 * time.Millisecond)
	if _, err := d.f.Read(buf); err != nil {
		fail("SHT40 gave no reading: %v", err)
		return
	}
	if crc8(buf[0:2]) != buf[2] || crc8(buf[3:5]) != buf[5] {
		fail("SHT40 reading fails its checksum: % x", buf)
		return
	}
	t := -45 + 175*float64(uint16(buf[0])<<8|uint16(buf[1]))/65535
	rh := -6 + 125*float64(uint16(buf[3])<<8|uint16(buf[4]))/65535
	pass("SHT40: %.1f C, %.0f %% relative humidity", t, rh)
}

func testOLED() {
	fmt.Printf("oled: bus %d\n", *headBus)
	d, err := openI2C(*headBus, 0x3c)
	if err != nil {
		fail("no /dev/i2c-%d or no access: %v (enable i2c%d with its m1 pins)", *headBus, err, *headBus)
		return
	}
	defer d.f.Close()
	// SSD1306, 128x64: on, horizontal addressing, whole screen as the window.
	setup := []byte{0xae, 0xd5, 0x80, 0xa8, 0x3f, 0xd3, 0x00, 0x40, 0x8d, 0x14, 0x20, 0x00, 0xa1, 0xc8, 0xda, 0x12,
		0x81, 0xcf, 0xd9, 0xf1, 0xdb, 0x40, 0xa4, 0xa6, 0x21, 0, 127, 0x22, 0, 7, 0xaf}
	for _, c := range setup {
		if _, err := d.f.Write([]byte{0x00, c}); err != nil {
			fail("SSD1306 at 0x3c does not answer: %v", err)
			return
		}
	}
	for page := 0; page < 8; page++ {
		row := []byte{0x40}
		for x := 0; x < 128; x++ {
			if (x/16+page)%2 == 0 { // 16-pixel squares
				row = append(row, 0xff)
			} else {
				row = append(row, 0x00)
			}
		}
		if _, err := d.f.Write(row); err != nil {
			fail("SSD1306 stopped answering: %v", err)
			return
		}
	}
	pass("SSD1306 answers; it should show a chessboard of 16-pixel squares")
}

// ---- input voltage ----

func testVin() {
	fmt.Println("vin: SARADC channel 1, VIN / 11")
	raws, _ := filepath.Glob("/sys/bus/iio/devices/iio:device*/in_voltage1_raw")
	if len(raws) == 0 {
		fail("no SARADC in /sys/bus/iio")
		return
	}
	raw, err1 := readNumber(raws[0])
	scale, err2 := readNumber(filepath.Join(filepath.Dir(raws[0]), "in_voltage_scale")) // mV per count
	if err1 != nil || err2 != nil {
		fail("cannot read the SARADC: %v %v", err1, err2)
		return
	}
	vin := raw * scale / 1000 * 11
	switch {
	case vin < 1:
		note("%.2f V: nothing on the jack or the terminal (powered over Type-C?)", vin)
	case vin < 8.5 || vin > 13.5:
		fail("%.2f V at VIN: outside 9 to 12.6 V, or the divider R1/R2 is wrong", vin)
	default:
		pass("%.2f V at VIN (the supply is about 0.4 V higher, before its diode)", vin)
	}
}

func readNumber(path string) (float64, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return 0, err
	}
	return strconv.ParseFloat(strings.TrimSpace(string(b)), 64)
}

// ---- GPIO, through sysfs ----

func gpio(n int, dir string) (string, error) {
	p := fmt.Sprintf("/sys/class/gpio/gpio%d", n)
	if _, err := os.Stat(p); err != nil {
		if err := os.WriteFile("/sys/class/gpio/export", []byte(strconv.Itoa(n)), 0); err != nil {
			return "", err
		}
	}
	return p, os.WriteFile(p+"/direction", []byte(dir), 0)
}

func level(p string) (int, error) {
	v, err := readNumber(p + "/value")
	return int(v), err
}

func busy(err error) bool { return errors.Is(err, syscall.EBUSY) }

func testLEDs() {
	fmt.Println("leds: NET and REC blink three times each; PWR is lit whenever the board's 3.3 V is on")
	for _, l := range []struct {
		name string
		n    int
	}{{"NET (blue)", gpioLedNet}, {"REC (red)", gpioLedRec}} {
		p, err := gpio(l.n, "out")
		if err != nil {
			fail("%s on gpio %d: %v", l.name, l.n, err)
			continue
		}
		for i := 0; i < 6; i++ {
			os.WriteFile(p+"/value", []byte(strconv.Itoa((i+1)%2)), 0)
			time.Sleep(300 * time.Millisecond)
		}
		note("%s blinked, if you saw it", l.name)
	}
}

func testButtons() {
	fmt.Println("buttons: each line rests high and goes low while pressed")
	for _, b := range []struct {
		name string
		n    int
	}{{"NET", gpioBtnNet}, {"STOP", gpioBtnStop}} {
		p, err := gpio(b.n, "in")
		if err != nil {
			fail("%s on gpio %d: %v", b.name, b.n, err)
			continue
		}
		if v, _ := level(p); v == 0 {
			fail("%s reads low without being pressed: pull-up missing, or the switch's legs are joined the other way", b.name)
			continue
		}
		fmt.Printf("        press %s within %v ...\n", b.name, *wait)
		pressed := false
		for end := time.Now().Add(*wait); time.Now().Before(end) && !pressed; time.Sleep(20 * time.Millisecond) {
			v, _ := level(p)
			pressed = v == 0
		}
		if pressed {
			pass("%s pressed", b.name)
		} else {
			fail("%s never went low", b.name)
		}
	}
	if p, err := gpio(gpioRtcInt, "in"); err != nil {
		note("RTC interrupt line on gpio %d: %v", gpioRtcInt, err)
	} else if v, _ := level(p); v == 1 {
		pass("RTC interrupt line rests high")
	} else {
		note("RTC interrupt line is low: an alarm flag is set in the DS3231, or R40 is missing")
	}
}

// ---- servos ----

func pwmChip(addr string) (string, error) {
	chips, _ := filepath.Glob("/sys/class/pwm/pwmchip*")
	for _, c := range chips {
		if dev, err := os.Readlink(c + "/device"); err == nil && strings.Contains(dev, addr) {
			return c, nil
		}
	}
	return "", fmt.Errorf("no PWM controller at %s: enable it with its m1 pins in the device tree", addr)
}

func testServo() {
	fmt.Println("servo: each goes to the middle, one end, the other end and back, then its pulses stop")
	for _, s := range []struct{ name, addr string }{{"pan", addrPwmPan}, {"tilt", addrPwmTilt}} {
		chip, err := pwmChip(s.addr)
		if err != nil {
			fail("%s: %v", s.name, err)
			continue
		}
		p := chip + "/pwm0"
		if _, err := os.Stat(p); err != nil {
			if err := os.WriteFile(chip+"/export", []byte("0"), 0); err != nil {
				fail("%s: %v", s.name, err)
				continue
			}
		}
		set := func(file, v string) error { return os.WriteFile(p+"/"+file, []byte(v), 0) }
		set("enable", "0")
		if err := set("period", "20000000"); err != nil { // 20 ms, in ns
			fail("%s: %v", s.name, err)
			continue
		}
		set("polarity", "normal")
		// 1.2 to 1.8 ms: well inside the travel, so nothing is driven against a stop.
		for i, us := range []int{1500, 1200, 1800, 1500} {
			set("duty_cycle", strconv.Itoa(us*1000))
			if i == 0 {
				set("enable", "1")
			}
			time.Sleep(900 * time.Millisecond)
		}
		set("enable", "0")
		note("%s swept, if you saw it move", s.name)
	}
}

// ---- card slot ----

func testSD() {
	fmt.Println("sd: the baseboard's card slot, on the SoC's second controller")
	if p, err := gpio(gpioCardDet, "in"); busy(err) {
		note("card-detect line is held by the kernel's driver, as it should be")
	} else if err == nil {
		v, _ := level(p)
		note("card-detect line reads %d (low means a card is in)", v)
	}
	hosts, _ := filepath.Glob("/sys/class/mmc_host/mmc*")
	host := ""
	for _, h := range hosts {
		if dev, err := os.Readlink(h + "/device"); err == nil && strings.Contains(dev, addrSdio) {
			host = h
		}
	}
	if host == "" {
		fail("no controller at %s: enable sdio with the sdmmc1m0 pins in the device tree", addrSdio)
		return
	}
	blocks, _ := filepath.Glob(host + "/mmc*:*/block/mmcblk*")
	if len(blocks) == 0 {
		fail("controller %s is up but sees no card", filepath.Base(host))
		return
	}
	card := filepath.Dir(filepath.Dir(blocks[0]))
	name, _ := os.ReadFile(card + "/name")
	if ios, err := os.ReadFile("/sys/kernel/debug/" + filepath.Base(host) + "/ios"); err == nil {
		for _, line := range strings.Split(string(ios), "\n") {
			if strings.HasPrefix(line, "clock") || strings.HasPrefix(line, "bus width") || strings.HasPrefix(line, "timing") {
				note("%s", line)
			}
		}
	}
	dev := "/dev/" + filepath.Base(blocks[0])
	os.WriteFile("/proc/sys/vm/drop_caches", []byte("3"), 0)
	f, err := os.Open(dev)
	if err != nil {
		fail("card %q found, but %s does not open: %v", strings.TrimSpace(string(name)), dev, err)
		return
	}
	defer f.Close()
	buf := make([]byte, 1<<20)
	start, total := time.Now(), 0
	for total < 32<<20 {
		n, err := f.Read(buf)
		total += n
		if err != nil {
			fail("read error after %d MiB: %v", total>>20, err)
			return
		}
	}
	pass("card %q: read %d MiB at %.1f MiB/s without an error", strings.TrimSpace(string(name)), total>>20,
		float64(total>>20)/time.Since(start).Seconds())
	note("run `dmesg | grep -i mmc` as well: CRC errors there mean the lines want a lower clock")
}

func main() {
	flag.Parse()
	tests := map[string]func(){"i2c": testI2C, "oled": testOLED, "vin": testVin, "leds": testLEDs,
		"buttons": testButtons, "servo": testServo, "sd": testSD}
	names := flag.Args()
	if len(names) == 0 {
		names = []string{"i2c", "oled", "vin", "leds", "buttons", "sd"}
	}
	for _, n := range names {
		t, ok := tests[n]
		if !ok {
			fmt.Fprintf(os.Stderr, "no test %q; there are: i2c oled vin leds buttons servo sd\n", n)
			os.Exit(2)
		}
		t()
	}
	if failed > 0 {
		fmt.Printf("%d failed\n", failed)
		os.Exit(1)
	}
	fmt.Println("nothing failed; what only eyes can judge is listed above")
}
