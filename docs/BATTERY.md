# Battery reference — Inkplate 5 Gen2 environment monitor

What changes when the device in [HARDWARE.md](HARDWARE.md) runs from its
battery instead of USB-C. Distilled from the datasheets on 2026-09-06. Every
section links its sources. Facts are from the datasheet unless marked
*(product page)*, *(schematic)*, *(derived)*, *(assumed)*, *(measured)* or
*(unverified)*.

> **Preliminary.** No current in this document has been measured on this
> device. The sleep floor, the ESP32 wake cost and the fan cost are the three
> numbers that set battery life, and each is an estimate. §10 says which PPK
> capture replaces which estimate. Treat every battery-life figure as an order
> of magnitude until then.

- [0. At a glance](#0-at-a-glance)
- [1. The battery](#1-the-battery)
- [2. The sensor regulator](#2-the-sensor-regulator)
- [3. Sleeping the sensors](#3-sleeping-the-sensors)
- [4. Why the sensor rail stays on](#4-why-the-sensor-rail-stays-on)
- [5. The wake cycle](#5-the-wake-cycle)
- [6. Current draw](#6-current-draw)
- [7. Battery life](#7-battery-life)
- [8. What sleeping costs in accuracy](#8-what-sleeping-costs-in-accuracy)
- [9. Firmware implications](#9-firmware-implications)
- [10. Measurement plan](#10-measurement-plan)
- [11. Open questions](#11-open-questions)
- [12. The decision, in plain terms](#12-the-decision-in-plain-terms)

---

## 0. At a glance

| | Mains build (HARDWARE.md) | Battery build (this doc) |
|---|---|---|
| Power in | USB-C | 1S LiPo on the JST-PH; USB-C charges it at ~400 mA |
| ESP32 | always awake | deep sleep, wakes every **5 min** |
| Sensor regulator | 3.3 V LDO ≥ 600 mA from the VIN pad | **TPS63020 buck-boost module** from the same VIN pad (§2) |
| Sensor rail | always on | **still always on** (§4) |
| PMSA003I fan | continuous | **SET → expander P1_3**; runs 35 s every 6th cycle (30 min) |
| SCD41 | periodic 5 s | **idle single shot** every 5 min, never powered down, ASC kept |
| BME688 | BSEC LP 3 s | **BSEC ULP 300 s**, state saved across sleep |
| SHTC3 | polled | one reading per wake |
| Extra wires | optional SET | SET (required), nothing else |
| Board changes | none | optional LED and regulator trims (§3) |

**What sets battery life, in order:** the PM fan (~60 % of the budget), the
ESP32 wake (25–65 %, unmeasured), everything else (< 10 %). The four sensors'
own sleep currents are not the problem; the boards they sit on and the fan are.

**Headline, primary design, 2000 mAh cell:** 5–11 days. See §7 before
choosing a cell.

---

## 1. The battery

Sources: [Inkplate 5V2 battery docs](https://docs.soldered.com/inkplate/5v2/hardware/battery/) ·
[schematic sheet 3/7](https://github.com/SolderedElectronics/Soldered-Inkplate-5-Gen2-hardware-design/blob/main/OUTPUTS/V1.1.0/Soldered%20Inkplate%205%20Gen2%20Schematics.pdf) ·
[TPS7A26 datasheet](https://www.ti.com/lit/ds/symlink/tps7a26.pdf) ·
[weather-cal power notes](../../inkplate10-weather-cal/doc/power-consumption.md)

### Connection

- **K4, JST-PH 2-pin, 2.0 mm.** Pin 1 is + *(schematic)*. Docs: "with the notch at the top, + is on the left". Docs also warn that vendor polarity varies and a reversed cell "may permanently damage your Inkplate" — check the cell's wiring against the board's + mark before plugging in.
- **Single-cell 3.7 V Li-ion / LiPo with a built-in protection circuit.** The board has no over-discharge cutoff of its own *(schematic: none on sheet 3)*; the docs require the cell to carry one.
- **Charger MCP73831T, R32 = 2.49 kΩ → 402 mA** *(schematic; I = 1000 V / R_PROG)*. USB present: the charger runs and the load runs from USB. No safety timer on this part.
- **Source selection is a P-MOSFET, not a diode** *(schematic, "AUTO SOURCE SELECTION")*: Q7 (SSM3J358R) connects VBAT to VIN when VUSB is absent; D10 (BAT20J) feeds VIN from VUSB when present. So **on battery, VIN = VBAT** minus a few tens of mV. Anything fed from the VIN pad sees the full cell voltage.
- **The Inkplate's own 3.3 V rail** is a TPS7A2633 LDO from VIN: dropout 92 mV typ at 100 mA, 173 mV at 250 mA, 355 mV at 500 mA; I_Q 2 µA. Below VBAT ≈ 3.5 V the ESP32 rail tracks the cell. This is normal for Inkplates and is what weather-cal runs on.

### Capacity and derating

| Cell | Charge time at 402 mA *(derived, ×1.3 for CV tail)* | Peak load as C-rate *(derived)* |
|---|---|---|
| 1200 mAh | ~4 h | 0.6 C |
| 2000 mAh | ~6.5 h | 0.4 C |
| 3000 mAh | ~10 h | 0.25 C |
| 6700 mAh | ~22 h | 0.1 C |

Peak load = ~470 mA sensors (§2) + ~300 mA ESP32 Wi-Fi TX *(HARDWARE.md §7)* ≈ 0.75 A from the cell. Any ordinary 1S cell rated ≥ 1 C handles it.

**Usable capacity is ~85 % of rated** *(assumed)*: the protection circuit cuts at 2.5–3.0 V, the firmware should stop at 3.1 V as weather-cal does, and the rated figure is at 0.2 C to 2.75 V. §7 shows raw and ×0.85. Self-discharge of ~2–3 %/month *(general figure)* only matters once life passes a month.

**Battery mAh ≈ load mAh.** From a 3.7 V cell an LDO at 3.3 V loses 11 % as heat; a buck-boost at ~90 % loses 10 %. Either way, one mAh drawn at 3.3 V costs about one mAh from the cell. The tables in §6–7 are in rail mAh and need no conversion.

---

## 2. The sensor regulator

Sources: [TPS63020](https://www.ti.com/lit/ds/symlink/tps63020.pdf) ·
[AP2112](https://cdn-shop.adafruit.com/product-files/2471/AP2112.pdf) ·
[Pololu S9V11F3S5](https://www.pololu.com/product/2872) · [S9V11F3S5C3](https://www.pololu.com/product/2873) ·
[Pololu D24V7F3](https://www.pololu.com/product/5592) · [Adafruit LM3671](https://www.adafruit.com/product/2745) ·
[SparkFun AP3429A](https://docs.sparkfun.com/SparkFun_Buck_Regulator_AP3429A/hardware_overview/)

HARDWARE.md §7 puts the sensors on their own 3.3 V regulator fed from the VIN
pad. That stays. What changes is the part: on battery, VIN is 3.0–4.2 V, and
the regulator's quiescent current runs 24 h a day.

### Requirements

| | Value | Why |
|---|---|---|
| Input | 3.0–4.2 V on battery, ~4.65 V on USB *(derived: VUSB − BAT20J)* | one wiring for both |
| Output | 3.3 V, ripple < 30 mV p-p unloaded | SCD41 datasheet |
| Peak | ≥ 470 mA (fan start 250 mA + SCD41 205 mA + BME688 17 mA) | HARDWARE.md §7 |
| Quiescent | as low as possible; every 100 µA is 2.4 mAh/day | §6 |
| Enable pin | not needed (§4), harmless to have | |

### Candidates

| Part | Topology | I_Q | Shutdown | Peak | Input | Verdict |
|---|---|---|---|---|---|---|
| **TPS63020 module** | buck-boost | **25 µA typ, 50 max** | 0.1 µA, load disconnect | 2 A | 1.8–5.5 V | **Use this.** Regulates across the whole cell curve. |
| **AP2112K-3.3** | LDO | 55 µA typ, 80 max | 0.01 µA, output auto-discharge | 600 mA | to 6 V | Good alternative. Dropout 250 mV typ / 400 max at 600 mA, 125/200 at 300 mA. Below VBAT ≈ 3.55 V it tracks the cell, as the Inkplate's own LDO does. Stable on 1 µF ceramic. |
| Pololu S9V11F3S5 | buck-boost | < 200 µA *(product page)* | 37 µA at 3.7 V | 1.5 A | 2–16 V | No. Quiescent is 8× the TPS63020 and equals the whole SCD41 idle budget. |
| Pololu S9V11F3S5C3 | same + 3.0 V cutoff | same | ~20 µA | | | No, same reason. Cutoff is nice but the cell's protection already does it. |
| SparkFun AP3429A | buck | 90 µA | < 1 µA | 2 A | 2.7–5.5 V | Workable; 3.6× the TPS63020 quiescent. |
| Adafruit LM3671 | buck | — | — | 600 mA | **3.5–5.5 V** | No. Minimum input is above most of the discharge curve. |
| Pololu D24V7F3 | buck | < 10 µA | — | 600 mA | **4–36 V** | No. Minimum input is above a full cell. |
| AMS1117-3.3 | LDO | **~5 mA** | — | 1 A | | No. 120 mAh/day doing nothing; 1.1 V dropout. Fine on mains only. |

### TPS63020 module

The bare part is a 3 × 4 mm QFN; use a module. Generic "TPS63020 3.3 V
buck-boost" boards are sold everywhere with the inductor and capacitors fitted
and a fixed 3.3 V output.

- **Wiring:** VIN pad → module IN; module OUT → the PMSA003I header VIN pin, as in HARDWARE.md §8. GND common.
- **EN:** tie to IN (module default on most boards). Not driven; see §4.
- **Power-save mode** is automatic at light load and is what gives the 25 µA figure. Some modules bring PS/SYNC out; leave it enabled.
- **Load disconnect** in shutdown: the output is isolated from the input. Irrelevant while EN is high.
- **Start-up current limit** ramps from 400 mA — the first fan start after power-on may take slightly longer to spin. Not an issue in operation.
- **Check the module for an LED** *(unverified — varies by seller)*. A power LED through 1 kΩ is ~1.3 mA and would be the single largest item in §6. Remove it.
- **Check ripple** on the rail during a fan start and an SCD41 pulse. The switcher runs at 2.4 MHz; with the module's ceramic output caps, ripple is normally well under the SCD41's 30 mV *(unverified)*. If not, add 22 µF at the SCD41 board's VIN.

### AP2112K-3.3 instead

If a module is hard to source, the AP2112K is a five-pin SOT-23 on any
SOT-23-5 breakout, plus 1 µF in and out. It is the same part the two Adafruit
boards already use. It costs 30 µA more per day than the TPS63020 (0.7 mAh/day)
and gives up the last ~10 % of the cell to dropout. The 50 mA "short current
limit" in the datasheet is foldback into a dead short, not the operating limit.

---

## 3. Sleeping the sensors

Sources: [SCD4x datasheet v1.7](https://sensirion.com/media/documents/48C4B7FB/67FE0194/CD_DS_SCD4x_Datasheet_D1.pdf) ·
[SCD4x low-power app note](https://sensirion.com/media/documents/077BC86F/62BF01B9/CD_AN_SCD4x_Low_Power_Operation_D1.pdf) ·
[Adafruit SCD-4X PCB](https://github.com/adafruit/Adafruit-SCD-4X-PCB) · [Adafruit PMSA003I PCB](https://github.com/adafruit/Adafruit-PMSA003I-PCB) ·
[Soldered BME688 docs](https://docs.soldered.com/bme688/hardware/) · [Soldered SHTC3 docs](https://docs.soldered.com/shtc3/hardware/)

### The dies

| Sensor | Sleep state | Current | Wake | What survives |
|---|---|---|---|---|
| **SCD41** | **idle** (not `power_down`) | **0.20 mA** | already awake; single shot 5 s | settings, ASC history, everything. See §4 for why not `power_down`. |
| PMSA003I | SET low | ≤ 200 µA *(product page)* | SET high, ≥ 30 s spin-up | nothing to keep |
| BME688 | sleep mode | 0.15 µA | forced measurement ~0.15 s | registers must be re-set; BSEC state lives in the ESP32 |
| SHTC3 | sleep 0xB098 | 0.3 µA | wakeup 0x3517, ~13 ms | nothing to keep |

The four dies asleep total **~400 µA**, and 200 of that is the PM module
standby *(product page)*, which has no lower state short of cutting its power.

### The boards

The dies are not what is on the rail. Each breakout adds its own always-on
parts. These are not in HARDWARE.md and none has been measured.

| Board | Always-on part | Current | Removable? |
|---|---|---|---|
| Adafruit 5190 (SCD41) | AP2112K regulator (pull-ups, shifter) | 55 µA typ | no |
| | green LED, 10 kΩ series *(schematic)* | ~120 µA *(derived)* | **yes — cut SJ3** |
| Adafruit 4632 (PMSA003I) | AP2112K regulator | 55 µA typ | no |
| | green LED, 10 kΩ series *(schematic)* | ~120 µA *(derived)* | desolder D1 or R1 — no jumper |
| Soldered 333203 (BME688) | regulator, part unknown | ~50 µA *(assumed)* | **yes — cut JP3, bridge JP2** *(HARDWARE.md §4; verify before cutting)* |
| | LED? | unknown | look at the board |
| Soldered 333032 (SHTC3) | regulator, part unknown | ~50 µA *(assumed)* | **yes — cut JP3, bridge JP4** *(inferred from the board layout; verify before cutting)* |
| | LED? | unknown | look at the board |

Board overhead: **~450 µA untrimmed, ~110 µA with the LEDs and Soldered
regulators out.** The trims are optional; §7 shows they are worth ~8 mAh/day at
the primary cadence, which is 5 % of the budget. They matter more at slower
cadences.

Bypassing a Soldered regulator puts the sensor and its level shifter straight
on the 3.3 V rail, which is what they run at anyway.

---

## 4. Why the sensor rail stays on

The obvious battery move is to switch the sensor rail off in deep sleep. Three
independent reasons not to.

**1. The SCD41 needs it on.** ASC — the drift correction that keeps CO₂
readings honest over months — works in *idle* single-shot mode and is disabled
in *power-cycled* single-shot mode, whether the cycling is by supply or by
`power_down`/`wake_up` *(datasheet §3.11; app note §2.4)*. The ASC history is
written to the sensor's EEPROM only after 48 idle shots with no power cycle
between *(app note §5.2)*. Cutting the rail every cycle means ASC never runs.

Sensirion's own break-even confirms it: power-cycling saves energy only when
the sampling period exceeds 380 s *(app note §2.4)*, because the first shot
after power-up must be discarded (154 mC vs 77 mC). At 5 minutes, idle is both
cheaper and calibrated.

**2. The pull-ups leak.** The Inkplate's 10 kΩ pull-ups to 3V3 have no jumper
*(HARDWARE.md §1)*. The Adafruit boards' 10 kΩ connector-side pull-ups go to
the sensor rail. With that rail at 0 V, each bus line is a 10 kΩ / 5 kΩ
divider: ~1.1 V on the bus, **~440 µA** of leak *(derived)*, and every unpowered
IC back-fed through its ESD diodes. That is more than the rail draws asleep.

**3. Isolating the bus costs more than it saves.** The natural fix is an
I²C buffer with an enable pin. The TCA9517 draws **1–5 mA** quiescent
*([datasheet](https://www.ti.com/lit/ds/symlink/tca9517.pdf))*. Analog switches
are cheaper but add a part to a chain that must stay open-drain and 5 V
tolerant. Not worth it for a rail that costs ~560 µA asleep.

So: rail on, EN tied high, every sensor put to sleep by command, the PM fan by
SET. Idle floor ~560 µA trimmed, ~900 µA untrimmed (§6).

---

## 5. The wake cycle

Sources: [Inkplate 5V2 deep sleep](https://docs.soldered.com/inkplate/5v2/low-power/deep-sleep/) ·
[PCAL6416A](https://www.nxp.com/docs/en/data-sheet/PCAL6416A.pdf) ·
[BSEC integration guide](https://afe.smartnydom.pl/pl/konfiguracja/konfiguracja-czujnikow/bosch-bmx/BST-BME680-AN008-45x.pdf) ·
[Bosch forum on ULP timing](https://community.bosch-sensortec.com/mems-sensors-forum-jrmujtaw/post/bsec-configuration-settings-ulp-ulp-plus-lp-3s-300s-clarification-XkL7VXKAc7pQGyy) ·
[weather-cal PPK capture](../../inkplate10-weather-cal/doc/power-consumption.md)

### Cadence: 5 minutes

Three parts agree on 300 s:

- **SCD41** ASC is "optimized for single shot measurements performed every 5 minutes"; shorter intervals wear the ASC EEPROM proportionally *(datasheet §3.11)*.
- **BSEC ULP** is built for a 300 s sample period with the MCU asleep between samples; the `generic_33v_300s_4d` config allows exactly that *(integration guide §1)*. Sample timing must stay within ±50 % of target, i.e. 150–450 s between BME688 measurements, or accuracy drops to 0 *(guide §3.2)*.
- The **wire contract**: the server's `X-Next-Refresh-Seconds` sets the cadence, as it does for weather-cal. It says 300.

### Fan: every 6th cycle, with the ESP32 asleep

The PM fan needs ≥ 30 s to spin up before a valid reading *(HARDWARE.md §3)*.
Keeping the ESP32 awake for that costs ~30 s × ~45 mA ≈ 0.37 mAh — more than
the whole rest of the wake. Instead:

1. **Wake A** (fan cycles only): boot, drive SET high on expander P1_3, deep sleep 30 s on the ESP32 timer. ~1 s awake.
2. **Wake B**: boot, read everything, SET low, network, render, deep sleep until the next 5-minute mark on the RTC alarm.

The PCAL6416A holds its output registers as long as VDD is present (1.0 µA
standby at 3.3 V), and it sits on the unswitched 3V3 *(HARDWARE.md §1)*, so SET
stays high through the ESP32's sleep.

### Wake B, in order

```
 0 s   boot; Inkplate::begin()          ← re-assert SET high first thing (§9)
 0.5 s SCD41 measure_single_shot        5 s, 175 mA pulse
       BME688 forced measurement        BSEC ULP; ~0.15 s heater
       SHTC3 wakeup, read, sleep        13 ms
       PMSA003I read, checksum          fan has been running 30 s
 5.5 s SCD41 read_measurement; SET low
       set_ambient_pressure from BME688 (RAM, no persist)
 6 s   Wi-Fi up → POST /readings → GET page → draw → Wi-Fi off
       BSEC state → RTC memory (every cycle), NVS (every ~6 h)
       RTC alarm for next 300 s mark; deep sleep
```

The sensor peaks may overlap. With their own 2 A regulator there is no reason
to serialise them; the ESP32's Wi-Fi is on the other rail. The ESP32 is awake
for the SCD41's 5 s plus whatever the network takes.

### What the ESP32 wake costs

The one measured figure is from the **Inkplate 10** running weather-cal
*(PPK2, June 2023)*: an 8.2 s window with 262 mC total and 3.7 mC in a 1.9 s
sleep, so **~41 mA awake, 124 mA peak**. At the 10–15 s awake time noted then,
that is **0.14 mAh per wake**. But weather-cal's own life predictions imply
**~0.79 mAh per wake**, and the capture may not include a panel refresh. This
document carries both as **floor / ceiling**. §10 item 4 closes the gap.

A wake without Wi-Fi or render — boot, sensors, back to sleep — is taken as
~7 s at ~45 mA ≈ **0.09 mAh** *(derived)*. Wake A is ~1 s ≈ **0.02 mAh**
*(derived)*.

---

## 6. Current draw

Primary design: 5-minute cycle, PM fan 35 s every 6th cycle, Wi-Fi and render
every wake, ESP32 wake at the floor figure, nothing trimmed. Per-cycle figures
average the fan over its 6 cycles. Rail mAh, which is ~battery mAh (§1).

| Device | Active mA | Active s / cycle | Sleep µA | mAh / 5-min cycle | mAh / h | mAh / day | mAh / week |
|---|---|---|---|---|---|---|---|
| Inkplate 5 Gen2 — wake B, floor | 41 | 12.5 | — | 0.140 | 1.680 | 40.3 | 282 |
| *Inkplate 5 Gen2 — wake B, ceiling (instead of floor)* | — | — | — | *0.790* | *9.480* | *227.5* | *1593* |
| Inkplate 5 Gen2 — wake A (fan start) | ~60 | ~1 | — | 0.003 | 0.040 | 1.0 | 7 |
| Inkplate 5 Gen2 — deep sleep | — | — | 24 | 0.002 | 0.024 | 0.6 | 4 |
| **PMSA003I — fan, every 6th cycle** | 200 | 35 | — | **0.324** | **3.889** | **93.3** | **653** |
| PMSA003I — standby, SET low | — | — | 200 | 0.017 | 0.200 | 4.8 | 34 |
| SCD41 — idle single shot | 175 pk | 5 | — | 0.021 | 0.257 | 6.2 | 43 |
| SCD41 — idle | — | — | 200 | 0.017 | 0.200 | 4.8 | 34 |
| BME688 — ULP sample | 12 | 0.15 | — | 0.008 | 0.090 | 2.2 | 15 |
| BME688 — sleep | — | — | 0.15 | 0.000 | 0.000 | 0.0 | 0 |
| SHTC3 — reading + sleep | 0.43 | 0.013 | 0.3 | 0.000 | 0.000 | 0.0 | 0 |
| TPS63020 — quiescent | — | — | 25 | 0.002 | 0.025 | 0.6 | 4 |
| Adafruit AP2112K ×2 — quiescent | — | — | 110 | 0.009 | 0.110 | 2.6 | 18 |
| SCD41 board LED (cut SJ3) | — | — | 120 | 0.010 | 0.120 | 2.9 | 20 |
| PM board LED (desolder) | — | — | 120 | 0.010 | 0.120 | 2.9 | 20 |
| Soldered regulators ×2 *(assumed)* (bypass) | — | — | 100 | 0.008 | 0.100 | 2.4 | 17 |
| **Total, floor, untrimmed** | | | **899** | **0.571** | **6.86** | **164.5** | **1152** |
| **Total, floor, trimmed** | | | **559** | **0.543** | **6.52** | **156.4** | **1095** |
| **Total, ceiling, trimmed** | | | 559 | 1.193 | 14.32 | **343.6** | **2405** |

Read the table this way: the fan is 93 of 156 mAh/day. The ESP32 wake is 40 —
or 228, if the ceiling is right. Every sensor die together is under 15. The
board overheads are 8. The Inkplate asleep is 0.6.

Mains, for comparison *(HARDWARE.md §7)*: ~315 mA continuous = 7 560 mAh/day.

---

## 7. Battery life

Days = capacity ÷ mAh/day. Each cell shows **raw / ×0.85 usable**. The floor
and ceiling rows bracket the unmeasured ESP32 wake; the truth is between them.

### Primary design

5-min cycle · PM every 30 min · Wi-Fi every wake · trimmed idle.

| ESP32 wake | mAh/day | 1200 mAh | 2000 mAh | 3000 mAh | 6700 mAh |
|---|---|---|---|---|---|
| floor 0.14 mAh | 156 | 8 / 7 | 13 / 11 | 19 / 16 | 43 / 36 |
| ceiling 0.79 mAh | 344 | 3 / 3 | 6 / 5 | 9 / 7 | 20 / 17 |

**One to two weeks on 2000 mAh.** This sensor set on battery is a
days-to-weeks device, not months. Below is what moves it.

### Cadence and fan interval

Trimmed idle. Each cell: floor / ceiling days.

| Cycle | PM every | mAh/day floor / ceil | 1200 mAh | 2000 mAh | 3000 mAh | 6700 mAh |
|---|---|---|---|---|---|---|
| 5 min | 5 min | 628 / 815 | 2 / 1 | 3 / 2 | 5 / 4 | 11 / 8 |
| **5 min** | **30 min** | **156 / 344** | **8 / 3** | **13 / 6** | **19 / 9** | **43 / 20** |
| 5 min | 60 min | 109 / 296 | 11 / 4 | 18 / 7 | 27 / 10 | 61 / 23 |
| 10 min | 30 min | 132 / 226 | 9 / 5 | 15 / 9 | 23 / 13 | 51 / 30 |
| 30 min | 30 min | 116 / 147 | 10 / 8 | 17 / 14 | 26 / 20 | 58 / 46 |
| 60 min | 60 min | 65 / 80 | 19 / 15 | 31 / 25 | 46 / 37 | 104 / 84 |

Raw days; multiply by 0.85 for usable.

### Levers, one at a time, on the primary design

| Change | mAh/day floor / ceil | 2000 mAh days | Note |
|---|---|---|---|
| none (baseline) | 156 / 344 | 13 / 6 | |
| Wi-Fi + render only every 6th wake; buffer readings in RTC memory | 144 / 176 | 14 / 11 | Small at the floor, halves the ceiling. Display then updates every 30 min. |
| leave LEDs and Soldered regulators in | 165 / 352 | 12 / 6 | 8 mAh/day |
| SCD41 `power_down` instead of idle | 152 / 339 | 13 / 6 | saves 5 mAh/day, **loses ASC** (§4). Not worth it. |
| fan spin-up 120 s instead of 30 s | 396 / 584 | 5 / 3 | if the "2–3 min to settle" report is right (§8) |
| **no PM sensor** | 54 / 242 | **37 / 8** | the fan is 60 % of the budget |
| AP2112K instead of TPS63020 | 157 / 344 | 13 / 6 | 0.7 mAh/day |

### Choosing a cell

At the primary design, each 1000 mAh buys 6 days (floor) to 3 days (ceiling).
A 6700 mAh cell reaches three to six weeks. The Inkplate's enclosure takes a
1200 mAh cell *(docs)*; anything larger needs the sensor bay to hold it.

Charging is the other constraint: 402 mA means a 6700 mAh cell takes most of a
day on USB (§1).

---

## 8. What sleeping costs in accuracy

| Sensor | Cost | Mitigation |
|---|---|---|
| **PMSA003I** | Intermittent use reads high; "2–3 min to settle" *(HARDWARE.md §3, unverified)*. 35 s may under-settle. | Measure: compare 35 s vs 120 s spin-up readings against continuous. If 120 s is needed, life halves (§7). |
| **SCD41** | None if kept in idle (§4). ASC needs ≥ 3 min of ~400 ppm air weekly *(HARDWARE.md §2)* — same as mains. | Single-shot noise is higher than periodic; average two shots if it matters (adds 77 mC). |
| **BME688** | BSEC accuracy takes ~20 min to reach 1 in ULP and hours to reach 3; restarts if state is lost *(HARDWARE.md §4)*. A cycle stretched past 450 s by a network retry drops accuracy to 0. | Read the BME688 before the network phase, at a fixed offset from wake. Persist state. |
| **SHTC3** | None. First reading after wake is valid. | |
| **All** | Temperature offsets change: the enclosure no longer has a warm always-on ESP32. | Re-measure the SCD41 offset in the finished enclosure, as HARDWARE.md §2 already requires. |

---

## 9. Firmware implications

Design constraints, not code. The mains loop in `main.cpp` is not the starting
point; weather-cal's sleep loop is.

- **Two wake sources.** Wake A → B is the ESP32 timer (`esp_sleep_enable_timer_wakeup`, 30 s). Wake B → next A/B is the RTC alarm (`rtcSetAlarmEpoch`, `enableWakeOnRtcAlarm`), so cycles land on 300 s marks regardless of how long wake B took. A cycle counter in RTC memory decides whether the next wake is A or B. Both are proven on this board *(measured 2026-09-09)*: the validation build arms the alarm and the timer together and wakes on `ESP_SLEEP_WAKEUP_EXT0`, so the design above no longer rests on an untested wake path.
- **`Inkplate::begin()` drives P1_3–P1_7 LOW** *(HARDWARE.md §1)*. Wake B must re-assert SET high before reading the PM sensor, or the fan stops the moment the board boots. Confirm what `begin()` does to the expander on wake.
- **SCD41: never `power_down`.** One `measure_single_shot` per wake. `set_ambient_pressure` each wake from the BME688 (RAM). `set_temperature_offset` and ASC period once, then `persist_settings` once. **Never `persist_settings` per wake** — the EEPROM is rated 2000 writes, which is a week at 5-minute cycles.
- **BSEC:** config `generic_33v_300s_4d`, ULP. State blob (238 B, HARDWARE.md §4) in RTC slow memory every cycle and in NVS every ~6 h; restore from RTC memory on wake, from NVS on cold boot. Timestamps in ns from the RTC epoch, never from `millis()`, so they stay monotonic across sleep.
- **BME688 before the network.** Its measurement must sit at a fixed offset from the 300 s mark (§8).
- **Battery cutoff** at 3.1 V via `readBattery()`, then a recharge notice and an unscheduled deep sleep — weather-cal's existing behaviour.
- **Readings POST** every wake as now, or buffered six-at-a-time in RTC memory and posted with the fan cycle (§7 lever). The server's `X-Next-Refresh-Seconds` is the cadence.
- **Network failures** must not stretch the cycle: give up fast, sleep to the next mark, keep the reading. The mains loop's 30 s retry-forever is wrong here.

---

## 10. Measurement plan

Each capture replaces an estimate. PPK2 in source-meter mode on the battery
connector, cell removed, unless stated.

| # | Capture | Replaces | Expect |
|---|---|---|---|
| 1 | Device asleep, rail on, all sensors asleep, SET low. 60 s. | **idle floor** (§3, §6) — catches board LEDs, regulator I_Q, module LED | 560–900 µA |
| 2 | As 1, LEDs and Soldered regulators trimmed. | the trim's value | −340 µA |
| 3 | One fan cycle: wake A, 30 s sleep, wake B to sleep. | **fan mAh**, wake A, PM input current at 3.3 V *(HARDWARE.md §11 q4)* | ~2.1 mAh |
| 4 | One wake B with Wi-Fi and render, cursor at boot / POST / GET / refresh / sleep. | **ESP32 wake, floor vs ceiling** — the largest open number | 0.14–0.79 mAh |
| 5 | One wake B without network or render. | sensor-only wake (0.09 mAh) | |
| 6 | Scope on the sensor rail during a fan start and an SCD41 pulse. | ripple against the 30 mV spec (§2) | |
| 7 | PM readings at 35 s and 120 s spin-up against a continuous run. | the spin-up assumption (§8) | |

Captures 1, 3 and 4 give the three numbers that set battery life. With those,
§7 becomes a prediction instead of a bracket.

---

## 11. Open questions

1. **ESP32 wake energy.** 0.14 or 0.79 mAh — a 5× spread that swings life 2× at the primary cadence. Capture 4.
2. **Panel refresh energy.** Unpublished for the ED052TC4 / TPS65186 and not separable in the Inkplate 10 capture. Capture 4.
3. **Soldered board LEDs and regulator parts.** Neither docs page mentions an LED; the hardware repo is not published. Look at the boards; measure (capture 1).
4. **TPS63020 module LED and ripple.** Seller-dependent. Capture 1 and 6.
5. **PM spin-up.** 35 s is the datasheet minimum; the field reports say minutes. Capture 7 decides whether the fan costs 2 or 7 mAh per run.
6. **Does `Inkplate::begin()` reset the expander on wake?** If it does, wake B loses the fan for a moment; if it reconfigures registers, SET must be restored before any PM read.
7. **Which cell.** Capacity, connector polarity and protection circuit, per §1.
8. **SCD41 breakout** is still assumed to be the Adafruit 5190 *(HARDWARE.md §11 q1)*. The LED, its jumper and the AP2112K figure in §3 depend on it.

---

## 12. The decision, in plain terms

Everything above, reduced to what to buy, what to change, and what the code
does. This is the plan until the PPK captures in §10 say otherwise.

### Buy

| Item | What exactly | Why |
|---|---|---|
| **1 × TPS63020 3.3 V buck-boost module** | any generic board with a fixed 3.3 V output; remove its power LED if it has one | powers the four sensors from the battery across its whole voltage range, 25 µA idle |
| **1 × battery** | single-cell 3.7 V LiPo, **with protection circuit**, JST-PH 2.0 mm plug, polarity checked against the board's + mark | 2000 mAh gives 1–2 weeks; 6700 mAh gives 3–6 weeks but needs ~22 h to charge and a bigger enclosure |
| 1 × 22 µF capacitor *(only if §10 capture 6 shows ripple > 30 mV)* | ceramic or tantalum, 6.3 V | keeps the SCD41 inside its supply spec |

Nothing else. No load switch, no I²C isolator, no second regulator.

### Wire

Same chain as HARDWARE.md §8, with two changes:

1. **Module in place of the LDO.** Inkplate VIN pad → module IN. Module OUT → PMSA003I header VIN. GND common. Module EN tied to IN.
2. **SET wire is now required**, not optional: PMSA003I SET → Inkplate expander **P1_3**.

The battery goes on K4. USB-C still charges it and takes over when plugged in;
nothing is rewired between mains and battery use.

### Change on the boards

| Board | Do | Effort |
|---|---|---|
| SCD41 (Adafruit 5190) | cut SJ3 — kills the power LED | knife |
| PMSA003I (Adafruit 4632) | desolder the green LED (D1) | iron, optional |
| BME688 (Soldered) | cut JP3, bridge JP2 — removes the board's regulator | knife + solder blob, optional |
| SHTC3 (Soldered) | cut JP3, bridge JP4 — removes the board's regulator *(inferred; verify)* | knife + solder blob, optional |

None of this is needed for the mains build, which cuts nothing (HARDWARE.md
§6). Together they save ~8 mAh/day — 5 % at the primary cadence. Do the cheap
ones; skip the iron work until capture 1 shows it matters.

The pull-up jumpers are deliberately absent from this list. Cutting JP5 or JP2
removes a 10 kΩ pull-up, and a pull-up passes current only while something
holds the line low. With the rail on and the bus idle high, they cost nothing,
so they buy no battery life. They are a bus rise-time choice, and only above
100 kHz.

### What the code does

Every **5 minutes**, on the RTC alarm:

1. Wake. Read the SHTC3, take one SCD41 single shot, take one BME688 sample. ~6 s.
2. Every **6th** wake, the PM sensor runs too: the board wakes 30 s early, turns the fan on, goes back to sleep, wakes again, reads PM, turns the fan off.
3. Connect Wi-Fi, POST the readings, GET the page, draw it, disconnect.
4. Save the BSEC state. Set the next alarm. Deep sleep.

Rules the code must keep:

- **Never power down the SCD41.** Leave it idle between shots. Never call `persist_settings` per wake.
- **Restore SET high first thing** after boot on a PM wake — `begin()` drives it low.
- **Read the BME688 before touching the network**, every wake, at the same offset. Late samples break BSEC.
- **Give up on the network fast.** A failed cycle sleeps to the next 5-minute mark; it does not retry for 30 s as the mains loop does.
- **Stop at 3.1 V** and show a recharge notice, as weather-cal does.

### What to expect

Three setups. All three keep the 5-minute cycle, so the SCD41 and BSEC stay
inside their timing rules (§5); they differ only in how often the fan runs and
how often the board talks to the server. Usable days (×0.85), **floor** /
ceiling for the ESP32 wake cost.

| Setup | Behaviour | mAh/day floor / ceil | 1200 mAh | 2000 mAh | 3000 mAh | 6700 mAh |
|---|---|---|---|---|---|---|
| **Conservative** | CO₂/T/RH every 5 min; PM every 2 h; panel and server update every 30 min | 74 / 105 | **14** / 10 | **23** / 16 | **35** / 24 | **77** / 54 |
| **Normal** | CO₂/T/RH every 5 min; PM every 30 min; panel and server update every 5 min | 156 / 344 | **7** / 3 | **11** / 5 | **16** / 7 | **36** / 17 |
| **Aggressive** | CO₂/T/RH every 5 min; PM every 10 min; panel and server update every 5 min | 345 / 532 | **3** / 2 | **5** / 3 | **7** / 5 | **17** / 11 |

- **Conservative** — about a month on 3000 mAh. The panel is up to 30 minutes behind the sensors; readings are buffered in RTC memory and posted six at a time. PM is a two-hourly trend, not a live number.
- **Normal** — the primary design in §5–7. About a fortnight on 3000 mAh. Everything on the panel is at most 5 minutes old.
- **Aggressive** — a week on 3000 mAh. PM every 10 minutes is the most the fan budget allows without going below a week.

Slower cycles (10, 30, 60 min) buy more, but break BSEC ULP's 150–450 s
timing rule and blunt ASC. They are only on the table if BSEC IAQ is given
up; §7 has those rows.

### If that is not enough

In order of what they buy, cheapest first. The Conservative setup is levers 1 and 2 applied to Normal:

1. **Run the PM sensor hourly** instead of every 30 min — +40 %.
2. **Post readings every 30 min** instead of every 5, buffering in between — up to +100 % if the wake cost is at the ceiling; the panel then updates every 30 min.
3. **Wake every 60 minutes** for everything — 2.4–4×, at the cost of CO₂ once an hour instead of every five minutes.
4. **Drop the PM sensor** — 1.4–3×.

### What would change this plan

- **Capture 1** shows the sleeping device over ~1.5 mA → something on a board is awake; find it before anything else.
- **Capture 4** shows the wake near 0.79 mAh → lever 2 becomes the first thing to do.
- **Capture 7** shows PM needs 120 s → the fan costs 3× more; PM goes hourly or goes.
