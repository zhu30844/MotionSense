#!/usr/bin/env python3
"""Writes baseboard.kicad_sch. The circuit is described at the bottom; edit it there."""
import math
import os
import re
import uuid

SYMDIR = "/usr/share/kicad/symbols"
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = "baseboard"
NS = uuid.UUID("6d4272cd-a45d-4626-b707-0632ee337942")
ROOT = str(uuid.uuid5(NS, "root"))

GND = "GND"
RAILS = {"VIN", "VSYS", "5V_BASE", "3V3_B", "V_SERVO"}
NC = "NC"

# Symbols KiCad does not ship.
LOCAL_SYMBOLS = {}

# LCSC part numbers, by reference first and then by value. Each was looked up on szlcsc.com.
LCSC = {
    "TPS54302": "C311983", "AP2112K-3.3": "C51118", "DS3231SN": "C9866", "24AA02E48T-I/OT": "C38987",
    "SHT40-AD1B": "C2909890","SS34": "C8678", "SMAJ15CA": "C110044", "3A hold": "C7500481", "10uH 6.5A": "C51933843",
    "220u 25V": "C2983317", "470u 16V": "C2977552", "10u 50V": "C13585", "22u 25V": "C12891", "100n": "C49678",
    "68p": "C2171219", "1u": "C28323", "2u2": "C49217",
    "100k": "C149504", "10k": "C17414", "1k": "C17513", "4k7": "C17673", "330": "C17630", "22": "C17561",
    "47k": "C17713", "13k": "C17455", "75k": "C17819", "51k": "C17737", "7k5": "C17807",
    "D4": "C181864", "D5": "C417350", "D6": "C99771",
    "J1": "C16214", "J2": "C474881", "J3": "C2905423", "J4": "C2905423", "J5": "C144395",
    "J6": "C2937625", "J7": "C2937625", "J8": "C2937625", "J9": "C2691448", "J10": "C114218",
    "BT1": "C964723", "SW1": "C5379895", "SW2": "C2837515", "SW3": "C2837515",
}

_libtext = {}
_symcache = {}
lib_symbols = {}
items = []
_done = set()
_pwr = [0]


def uid(*parts):
    return str(uuid.uuid5(NS, "/".join(str(p) for p in parts)))


def block(text, start):
    depth = 0
    for j in range(start, len(text)):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return text[start : j + 1]
    raise ValueError("unbalanced")


def lib_block(lib, name):
    if lib not in _libtext:
        _libtext[lib] = open(os.path.join(SYMDIR, lib + ".kicad_sym")).read()
    text = _libtext[lib]
    return block(text, text.index('\n\t(symbol "%s"\n' % name) + 2)


def load(lib_id):
    """Returns the pins of a symbol and records its definition for embedding."""
    if lib_id in _symcache:
        return _symcache[lib_id]
    lib, name = lib_id.split(":")
    if lib == PROJECT:
        body = LOCAL_SYMBOLS[name]
    else:
        body = lib_block(lib, name)
        parent = re.search(r'\(extends "([^"]*)"\)', body)
        if parent:
            child = body
            body = lib_block(lib, parent.group(1)).replace('(symbol "%s' % parent.group(1), '(symbol "%s' % name)
            for m in re.finditer(r'\(property "([^"]*)"', child):
                old = re.search(r'\(property "%s"' % re.escape(m.group(1)), body)
                new = block(child, m.start())
                body = body.replace(block(body, old.start()), new) if old else body
    lib_symbols[lib_id] = body.replace('(symbol "%s"' % name, '(symbol "%s"' % lib_id, 1)
    pins = []
    for m in re.finditer(r"\(pin (\w+) \w+", body):
        p = block(body, m.start())
        x, y, a = re.search(r"\(at ([-\d.]+) ([-\d.]+) (\d+)\)", p).groups()
        number = re.search(r'\(number "([^"]*)"', p).group(1)
        pins.append((number, m.group(1), float(x), float(y), int(a)))
    _symcache[lib_id] = pins
    return pins


def rnd(v):
    return round(v + 0.0, 4)


def prop(name, value, x, y, hide=False, justify=None, angle=0):
    eff = "(font (size 1.27 1.27))"
    if justify:
        eff += " (justify %s)" % justify
    if hide:
        eff += " (hide yes)"
    return '\t\t(property "%s" "%s" (at %s %s %s) (effects %s))\n' % (name, value, rnd(x), rnd(y), angle, eff)


def wire(x1, y1, x2, y2):
    items.append(
        "\t(wire (pts (xy %s %s) (xy %s %s)) (stroke (width 0) (type default)) (uuid \"%s\"))\n"
        % (rnd(x1), rnd(y1), rnd(x2), rnd(y2), uid("w", x1, y1, x2, y2))
    )


def text(s, x, y, size=2.0):
    items.append(
        '\t(text "%s" (exclude_from_sim no) (at %s %s 0) (effects (font (size %s %s)) (justify left bottom)) (uuid "%s"))\n'
        % (s, x, y, size, size, uid("t", s, x, y))
    )


def instance(lib_id, ref, value, x, y, rot=0, mirror=False, fp="", refat=None, valat=None, show_value=True, pins=None):
    s = "\t(symbol (lib_id \"%s\") (at %s %s %s)%s (unit 1)\n" % (lib_id, rnd(x), rnd(y), rot, " (mirror y)" if mirror else "")
    s += "\t\t(exclude_from_sim no) (in_bom %s) (on_board yes) (dnp no)\n" % ("no" if ref[:2] in ("TP", "JP") else "yes")
    s += '\t\t(uuid "%s")\n' % uid("s", ref)
    rx, ry, rj = refat or (x, y - 2.54, None)
    vx, vy, vj = valat or (x, y + 2.54, None)
    turn = 90 if rot in (90, 270) else 0
    if rot in (90, 180):
        flip = {"left": "right", "right": "left", None: None}
        rj, vj = flip[rj], flip[vj]
    s += prop("Reference", ref, rx, ry, hide=ref.startswith("#"), justify=rj, angle=turn)
    s += prop("Value", value, vx, vy, hide=not show_value, justify=vj, angle=turn)
    s += prop("Footprint", fp, x, y, hide=True)
    s += prop("Datasheet", "", x, y, hide=True)
    if not ref.startswith("#") and ref[:2] not in ("TP", "JP"):
        s += prop("LCSC", LCSC.get(ref) or LCSC[value], x, y, hide=True)
    for number in pins or []:
        s += '\t\t(pin "%s" (uuid "%s"))\n' % (number, uid("p", ref, number))
    s += '\t\t(instances (project "%s" (path "/%s" (reference "%s") (unit 1))))\n\t)\n' % (PROJECT, ROOT, ref)
    items.append(s)


def power(net, x, y, d):
    """Power symbol for a rail or ground, body pointing along d."""
    _pwr[0] += 1
    ref = "#PWR%03d" % _pwr[0]
    if net == GND:
        rot = {(0, 1): 0, (1, 0): 90, (0, -1): 180, (-1, 0): 270}[d]
        instance("power:GND", ref, GND, x, y, rot, show_value=False, pins=["1"])
        load("power:GND")
        return
    rot = {(0, -1): 0, (-1, 0): 90, (0, 1): 180, (1, 0): 270}[d]
    # Left-pointing rails sit beside connector labels, so their name goes past them.
    reach = (12 if d[0] < 0 else 4.6) + 0.55 * len(net) if d[0] else 4.6
    instance("power:VCC", ref, net, x, y, rot, valat=(x + d[0] * reach, y + d[1] * reach, None), pins=["1"])
    load("power:VCC")


def connect(net, x, y, d, side=(-1, 0)):
    """Ties the point (x, y), whose free side faces d, to a net; labels on upright pins leave towards side."""
    key = (net, rnd(x), rnd(y))
    if key in _done:
        return
    _done.add(key)
    if net == NC:
        items.append('\t(no_connect (at %s %s) (uuid "%s"))\n' % (rnd(x), rnd(y), uid("nc", x, y)))
        return
    if net == GND or net in RAILS:
        natural = (0, 1) if net == GND else (0, -1)
        if d == natural:
            power(net, x, y, d)
        else:
            ex, ey = x + d[0] * 2.54, y + d[1] * 2.54
            wire(x, y, ex, ey)
            power(net, ex, ey, d)
        return
    if d[0] == 0:
        d = side
    ex, ey = x + d[0] * 2.54, y + d[1] * 2.54
    wire(x, y, ex, ey)
    angle, just = {(1, 0): (0, "left"), (-1, 0): (180, "right"), (0, -1): (90, "left"), (0, 1): (270, "right")}[d]
    items.append(
        '\t(label "%s" (at %s %s %s) (effects (font (size 1.27 1.27)) (justify %s bottom)) (uuid "%s"))\n'
        % (net, rnd(ex), rnd(ey), angle, just, uid("l", net, ex, ey))
    )


def place(lib_id, ref, value, x, y, nets, rot=0, mirror=False, fp="", refat=None, valat=None, show_value=True):
    pins = load(lib_id)
    instance(lib_id, ref, value, x, y, rot, mirror, fp, refat, valat, show_value, pins=[p[0] for p in pins])
    c, s = round(math.cos(math.radians(rot))), round(math.sin(math.radians(rot)))
    for number, kind, px, py, pa in pins:
        ox, oy = -round(math.cos(math.radians(pa))), -round(math.sin(math.radians(pa)))
        if mirror:
            px, ox = -px, -ox
        qx, qy = px * c - py * s, px * s + py * c
        dx, dy = ox * c - oy * s, ox * s + oy * c
        if kind == "no_connect":
            continue
        if number not in nets:
            raise SystemExit("%s pin %s has no net" % (ref, number))
        net = nets[number]
        if isinstance(net, tuple):
            connect(net[0], x + qx, y - qy, (dx, -dy), net[1])
        else:
            connect(net, x + qx, y - qy, (dx, -dy))


R0805 = "Resistor_SMD:R_0805_2012Metric_Pad1.20x1.40mm_HandSolder"
C0805 = "Capacitor_SMD:C_0805_2012Metric_Pad1.18x1.45mm_HandSolder"
C1206 = "Capacitor_SMD:C_1206_3216Metric_Pad1.33x1.80mm_HandSolder"
CPOL = "Capacitor_SMD:CP_Elec_6.3x7.7"
LED3 = "LED_THT:LED_D3.0mm_Horizontal_O1.27mm_Z2.0mm"  # 3 mm, legs bent to look through the front wall
SMA = "Diode_SMD:D_SMA"
IND = "baseboard:IND-SMD_L7.5-W6.6_GSM0650"
# Footprints in baseboard.pretty were fetched by LCSC number with easyeda2kicad.
SOCKET = "baseboard:HDR-TH_20P-P2.54-V-F-2"
HDR = "Connector_PinHeader_2.54mm:PinHeader_1x%02d_P2.54mm_Vertical"


def vert(lib_id, ref, value, x, y, top, bottom, fp):
    """Two-pin part drawn upright, pin 1 on top."""
    place(lib_id, ref, value, x, y, {"1": top, "2": bottom}, fp=fp, refat=(x + 2.2, y - 1.3, "left"), valat=(x + 2.2, y + 1.3, "left"))


def horiz(lib_id, ref, value, x, y, left, right, fp, rot=90):
    """Two-pin part drawn lying down; for upright symbols pin 1 is on the left."""
    nets = {"1": right, "2": left} if rot == 180 else {"1": left, "2": right}
    place(lib_id, ref, value, x, y, nets, rot=rot, fp=fp, refat=(x, y - 3.2, None), valat=(x, y + 3.4, None))


def R(ref, value, x, y, top, bottom):
    vert("Device:R", ref, value, x, y, top, bottom, R0805)


def C(ref, value, x, y, top, bottom=GND, fp=C0805):
    vert("Device:C", ref, value, x, y, top, bottom, fp)


def buck(n, x, y, out, r_bottom, ref0):
    """TPS54302 stage; ref0 is the first reference number of its passives."""
    sw, bst, fb = "SW%d" % n, "BST%d" % n, "FB%d" % n
    place("Regulator_Switching:TPS54302", "U%d" % n, "TPS54302", x, y,
          {"1": GND, "2": sw, "3": "VIN", "4": fb, "5": "UVLO", "6": bst},
          fp="Package_TO_SOT_SMD:SOT-23-6", refat=(x - 7.6, y - 7.6, "left"), valat=(x + 1.3, y - 7.6, "left"))
    C("C%d" % ref0, "10u 50V", x - 38.1, y + 7.62, "VIN", fp=C1206)
    C("C%d" % (ref0 + 1), "100n", x - 25.4, y + 7.62, "VIN")
    horiz("Device:C", "C%d" % (ref0 + 2), "100n", x + 30.48, y - 12.7, bst, sw, C0805)
    horiz("Device:L", "L%d" % n, "10uH 6.5A", x + 30.48, y, sw, out, IND)
    R("R%d" % ref0, "100k", x + 58.42, y + 7.62, out, fb)
    R("R%d" % (ref0 + 1), r_bottom, x + 58.42, y + 25.4, fb, GND)
    C("C%d" % (ref0 + 3), "22u 25V", x + 71.12, y + 7.62, out, fp=C1206)
    C("C%d" % (ref0 + 4), "22u 25V", x + 83.82, y + 7.62, out, fp=C1206)
    C("C%d" % (ref0 + 5), "68p", x + 96.52, y + 7.62, out, fb)


# ---- Power input -----------------------------------------------------------
text("POWER INPUT  9-12.6 V battery or 12 V adapter, the higher one feeds", 20, 25)
place("Connector:Barrel_Jack_Switch", "J1", "DC 5.5x2.1", 30.48, 43.18, {"1": "VJACK", "2": GND, "3": NC},
      fp="baseboard:DC-IN-TH_DC-005-5.5-2.0", refat=(30.48, 35.6, None), valat=(30.48, 50.8, None))
place("Connector:Screw_Terminal_01x02", "J2", "BATTERY 3S", 30.48, 66.04, {"1": "VBAT", "2": GND}, mirror=True,
      fp="baseboard:CONN-TH_P5.00_KF301-5.0-2P",
      refat=(30.48, 60.9, None), valat=(30.48, 73.7, None))
horiz("Diode:SS34", "D1", "SS34", 68.58, 40.64, "VJACK", "VIN_OR", SMA, rot=180)
horiz("Diode:SS34", "D7", "SS34", 68.58, 66.04, "VBAT", "VIN_OR", SMA, rot=180)
horiz("Device:Polyfuse", "F1", "3A hold", 104.14, 45.72, "VIN_OR", "VIN", "Fuse:Fuse_1812_4532Metric_Pad1.30x3.40mm_HandSolder")
# Latching push button: out holds UVLO low and both regulators stop.
# Its drawing (8.5-8.5 ZS): pin 2 is the common, joined to pin 3 when out and to pin 1 when pushed in.
place("Switch:SW_SPDT", "SW1", "POWER latching", 149.86, 45.72, {"1": NC, "2": "UVLO", "3": GND},
      fp="baseboard:SW-TH_6P-8.5-8.5-ZS", refat=(149.86, 38.1, None), valat=(149.86, 53.3, None))
text("SW1 carries no load current; released = off", 130, 58, 1.27)
place("Diode:SMAJ15A", "D2", "SMAJ15CA", 96.52, 68.58, {"1": "VIN", "2": GND}, rot=270, fp=SMA,
      refat=(98.8, 67.3, "left"), valat=(98.8, 69.9, "left"))
vert("Device:C_Polarized", "C1", "220u 25V", 111.76, 68.58, "VIN", GND, CPOL)
R("R1", "100k", 134.62, 68.58, "VIN", "VIN_SENSE")
R("R2", "10k", 134.62, 86.36, "VIN_SENSE", GND)
C("C2", "100n", 152.4, 86.36, "VIN_SENSE")
R("R3", "51k", 172.72, 68.58, "VIN", "UVLO")
R("R4", "7k5", 172.72, 86.36, "UVLO", GND)
text("VIN_SENSE = VIN / 11, read on SARADC_IN1", 120, 99, 1.27)
text("UVLO: start 9.5 V, stop 8.8 V at VIN (battery about 0.4 V higher)", 120, 102, 1.27)

# ---- Regulators ------------------------------------------------------------
text("SYSTEM 5.2 V  (4.85 V at VSYS after D3)", 190, 25)
buck(1, 228.6, 45.72, "5V_BASE", "13k", 10)
horiz("Diode:SS34", "D3", "SS34", 365.76, 45.72, "5V_BASE", "VSYS", SMA, rot=180)
text("D3 lets the Pro Max Type-C and this board both feed VSYS", 340, 66, 1.27)

text("SERVO 5.2 V  (close JP1 for 6 V)", 190, 100)
buck(2, 228.6, 120.65, "V_SERVO", "13k", 20)
R("R22", "75k", 261.62, 163.83, "FB2", "FB2_6V")
horiz("Jumper:SolderJumper_2_Open", "JP1", "6V", 281.94, 172.72, "FB2_6V", GND,
      "Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm", rot=0)
vert("Device:C_Polarized", "C26", "470u 16V", 337.82, 128.27, "V_SERVO", GND, CPOL)

text("BOARD 3.3 V  follows the Pro Max 3.3 V", 20, 110)
place("Regulator_Linear:AP2112K-3.3", "U3", "AP2112K-3.3", 60.96, 127, {"1": "VSYS", "2": GND, "3": "3V3_CORE", "5": "3V3_B"},
      fp="Package_TO_SOT_SMD:SOT-23-5", refat=(55.9, 119.4, "left"), valat=(60.96, 119.4, "left"))
C("C30", "1u", 20.32, 137.16, "VSYS")
R("R30", "100k", 43.18, 142.24, "3V3_CORE", GND)
C("C31", "2u2", 83.82, 137.16, "3V3_B")
for i, (name, colour, net) in enumerate([("PWR", "green", "3V3_B"), ("NET", "blue", "LED_NET"), ("REC", "red", "LED_REC")]):
    x = 104.14 + i * 30.48
    R("R%d" % (31 + i), "330" if colour == "blue" else "1k", x, 132.08, net, "LED_%s_A" % name)  # blue drops about 2.8 V
    place("Device:LED", "D%d" % (4 + i), "%s %s" % (name, colour), x, 149.86, {"1": GND, "2": "LED_%s_A" % name}, rot=90,
          fp=LED3, refat=(x + 2.5, 148.6, "left"), valat=(x + 2.5, 151.2, "left"))

# ---- Pro Max socket --------------------------------------------------------
text("PRO MAX  (J4 pin n is header pin n + 20)", 172, 185)
place("Connector:Conn_01x20_Socket", "J3", "PINS 1-20", 193.04, 226.06, {
    "1": "UART2_TX", "2": "UART2_RX", "3": GND, "4": "PWM_TILT", "5": "PWM_PAN", "6": "BTN_STOP", "7": "BTN_NET",
    "8": GND, "9": "I2C3_SDA", "10": "I2C3_SCL", "11": "I2C1_SDA", "12": "LED_NET", "13": GND, "14": "LED_REC",
    "15": NC, "16": "RTC_INT", "17": "I2C1_SCL", "18": GND, "19": "UART3_TX", "20": "UART3_RX"},
    fp=SOCKET, refat=(194.3, 198.1, None), valat=(194.3, 254, None))
place("Connector:Conn_01x20_Socket", "J4", "PINS 21-40", 210.82, 226.06, {
    "1": "SDIO_D3", "2": "SDIO_D2", "3": GND, "4": "SDIO_D1", "5": "SDIO_D0", "6": "SDIO_CLK", "7": "SDIO_CMD",
    "8": GND, "9": "SD_CD", "10": NC,
    "11": NC, "12": "VIN_SENSE", "13": GND, "14": NC, "15": NC, "16": "3V3_CORE", "17": NC, "18": GND,
    "19": "VSYS", "20": NC}, mirror=True,
    fp=SOCKET, refat=(209.5, 198.1, None), valat=(209.5, 254, None))

# ---- I2C3: RTC, MAC address, temperature and humidity -----------------------
text("I2C3  RTC 0x68, MAC 0x50, T/RH 0x44", 20, 185)
place("Timer_RTC:DS3231M", "U4", "DS3231SN", 58.42, 215.9,
      dict({"1": NC, "2": "3V3_B", "3": "RTC_INT", "4": NC, "14": ("VBAT_RTC", (1, 0)), "15": "I2C3_SDA", "16": "I2C3_SCL"},
           **{str(n): GND for n in range(5, 14)}),
      fp="Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm", refat=(60.96, 229.9, "left"), valat=(60.96, 227.3, "left"))
place("Device:Battery_Cell", "BT1", "CR1220", 93.98, 213.36, {"1": "VBAT_RTC", "2": GND},
      fp="baseboard:BAT-SMD_BS-12-B3AA011", refat=(96.5, 210.8, "left"), valat=(96.5, 213.4, "left"))
C("C40", "100n", 20.32, 213.36, "3V3_B")
R("R40", "10k", 116.84, 205.74, "3V3_B", "RTC_INT")
R("R41", "4k7", 137.16, 205.74, "3V3_B", "I2C3_SDA")
R("R42", "4k7", 157.48, 205.74, "3V3_B", "I2C3_SCL")
place("Connector:TestPoint", "TP1", "SDA", 139.7, 228.6, {"1": "I2C3_SDA"}, fp="TestPoint:TestPoint_Pad_D1.5mm",
      refat=(141.7, 223.5, "left"), valat=(141.7, 226.1, "left"))
place("Connector:TestPoint", "TP2", "SCL", 139.7, 241.3, {"1": "I2C3_SCL"}, fp="TestPoint:TestPoint_Pad_D1.5mm",
      refat=(141.7, 236.2, "left"), valat=(141.7, 238.8, "left"))
place("Memory_EEPROM:24AA02E-OT", "U5", "24AA02E48T-I/OT", 40.64, 259.08, {"1": "I2C3_SCL", "2": GND, "3": "I2C3_SDA", "4": "3V3_B"},
      fp="Package_TO_SOT_SMD:SOT-23-5", refat=(43.2, 250.2, "left"), valat=(43.2, 267.9, "left"))
C("C41", "100n", 20.32, 259.08, "3V3_B")
place("Sensor_Humidity:SHT4x", "U6", "SHT40-AD1B", 106.68, 259.08, {"1": "I2C3_SDA", "2": "I2C3_SCL", "3": "3V3_B", "4": GND},
      fp="Sensor_Humidity:Sensirion_DFN-4_1.5x1.5mm_P0.8mm_SHT4x_NoCentralPad",
      refat=(111.8, 250.2, "left"), valat=(111.8, 267.9, "left"))
C("C42", "100n", 129.54, 259.08, "3V3_B")

# ---- Pan-tilt head, servos, serial ports ------------------------------------
text("HEAD OLED  I2C1, own bus", 245, 185)
place("Connector:Conn_01x04_Pin", "J5", "HEAD OLED", 271.78, 200.66, {"1": GND, "2": "3V3_B", "3": "I2C1_SCL", "4": "I2C1_SDA"},
      mirror=True, fp="baseboard:CONN-TH_B4B-XH-A-LF-SN", refat=(274.3, 194.3, "left"), valat=(274.3, 209.6, "left"))
R("R50", "4k7", 294.64, 200.66, "3V3_B", "I2C1_SCL")
R("R51", "4k7", 314.96, 200.66, "3V3_B", "I2C1_SDA")

text("SERVOS  GND, V+, signal", 245, 220)
for i, name in enumerate(["PAN", "TILT"]):
    y = 229.87 + i * 15.24
    place("Connector:Conn_01x03_Pin", "J%d" % (6 + i), name, 271.78, y, {"1": GND, "2": "V_SERVO", "3": "SERVO_" + name},
          mirror=True, fp=HDR % 3, refat=(274.3, y - 1.3, "left"), valat=(274.3, y + 1.3, "left"))
    horiz("Device:R", "R%d" % (52 + i), "330", 302.26, y, "PWM_" + name, "SERVO_" + name, R0805)

text("SERIAL", 345, 100)
place("Connector:Conn_01x03_Pin", "J8", "DEBUG UART2", 373.38, 113.03, {"1": GND, "2": "UART2_TX", "3": "UART2_RX"},
      mirror=True, fp=HDR % 3, refat=(375.9, 109.2, "left"), valat=(375.9, 118.7, "left"))
place("Connector:Conn_01x04_Pin", "J9", "SPARE UART3", 373.38, 138.43, {"1": GND, "2": "3V3_B", "3": "UART3_TX", "4": "UART3_RX"},
      mirror=True, fp=HDR % 4, refat=(375.9, 132.1, "left"), valat=(375.9, 147.3, "left"))

text("BUTTONS", 335, 185)
for i, (name, net) in enumerate([("NETWORK", "BTN_NET"), ("SAFE STOP", "BTN_STOP")]):
    y = 200.66 + i * 25.4
    place("Switch:SW_Push", "SW%d" % (2 + i), name, 350.52, y, {"1": net, "2": GND},
          fp="baseboard:SW-TH_4P-L6.0-W6.0-P4.50-LS6.5", refat=(350.52, y - 6.4, None), valat=(350.52, y + 3.8, None))
    R("R%d" % (54 + i), "10k", 375.92, y - 2.54, "3V3_B", net)
    C("C%d" % (50 + i), "100n", 393.7, y + 7.62, net)

# ---- Card slot on the second controller (GPIO2_A0-A5, detect on A6) ----------
text("CARD SLOT  recordings; controller sdio, pins sdmmc1m0", 430, 25)
place("Connector:Micro_SD_Card_Det_Hirose_DM3AT", "J10", "DM3AT-SF-PEJM5", 520.7, 60.96, {
    "1": "SD_D2", "2": "SD_D3", "3": "SD_CMD", "4": "3V3_B", "5": "SD_CLK", "6": GND, "7": "SD_D0", "8": "SD_D1",
    "9": GND, "10": "SD_CD", "SH": GND},
    fp="Connector_Card:microSD_HC_Hirose_DM3AT-SF-PEJM5", refat=(520.7, 43.2, None), valat=(520.7, 80, None))
for i, name in enumerate(["CLK", "CMD", "D0", "D1", "D2", "D3"]):
    horiz("Device:R", "R%d" % (60 + i), "22", 452.12, 104.14 + i * 10.16, "SDIO_" + name, "SD_" + name, R0805)
for i, name in enumerate(["CMD", "D0", "D1", "D2", "D3"]):
    R("R%d" % (66 + i), "47k", 490.22 + i * 17.78, 114.3, "3V3_B", "SD_" + name)
R("R71", "10k", 490.22, 144.78, "3V3_B", "SD_CD")
C("C60", "100n", 508, 144.78, "3V3_B")
C("C61", "10u 50V", 525.78, 144.78, "3V3_B", fp=C1206)
text("Series resistors sit next to the Pro Max socket", 430, 170, 1.27)

# ---- Power flags, so the rule check knows these nets are driven --------------
text("FLAGS", 20, 162, 1.27)
for i, net in enumerate(["VIN", "VSYS", "5V_BASE", "V_SERVO", GND]):
    x = 38.1 + i * 17.78
    instance("power:PWR_FLAG", "#FLG%02d" % (i + 1), "PWR_FLAG", x, 167.64, valat=(x, 162.6, None), pins=["1"])
    load("power:PWR_FLAG")
    wire(x, 167.64, x, 170.18)
    connect(net, x, 170.18, (0, 1))
place("power:PWR_FLAG", "#FLG06", "PWR_FLAG", 78.74, 196.85, {"1": "VBAT_RTC"}, valat=(78.74, 192, None))


def main():
    out = '(kicad_sch\n\t(version 20250114)\n\t(generator "eeschema")\n\t(generator_version "9.0")\n'
    out += '\t(uuid "%s")\n\t(paper "A2")\n' % ROOT
    out += '\t(title_block (title "MotionSense Pro Max baseboard") (rev "0.1") (comment 1 "Generated by gen_sch.py"))\n'
    out += "\t(lib_symbols\n" + "".join("\t\t%s\n" % lib_symbols[k] for k in sorted(lib_symbols)) + "\t)\n"
    out += "".join(items)
    out += '\t(sheet_instances (path "/" (page "1")))\n\t(embedded_fonts no)\n)\n'
    open(os.path.join(HERE, PROJECT + ".kicad_sch"), "w").write(out)
    lib = '(kicad_symbol_lib\n\t(version 20241209)\n\t(generator "gen_sch")\n'
    lib += "".join("\t%s\n" % LOCAL_SYMBOLS[k] for k in sorted(LOCAL_SYMBOLS)) + ")\n"
    open(os.path.join(HERE, PROJECT + ".kicad_sym"), "w").write(lib)
    table = '(sym_lib_table\n\t(version 7)\n\t(lib (name "%s")(type "KiCad")(uri "${KIPRJMOD}/%s.kicad_sym")(options "")(descr ""))\n)\n'
    open(os.path.join(HERE, "sym-lib-table"), "w").write(table % (PROJECT, PROJECT))


main()
