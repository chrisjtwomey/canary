// The bench routine: the sensors instead of the awake loop.
//
// One pass over the bus and the four parts every wake, then ten seconds of
// deep sleep and round again. It says which addresses answered, whether each
// sensor reads sensibly running and in the low-power state docs/BATTERY.md 3
// gives it, and takes one reading set from them all. There is no network and
// no panel, so what the serial log shows is the wiring and nothing else.
//
//   pio run -e esp32-validate -t upload && pio device monitor -b 115200
//
// The phase markers carry milliseconds so a PPK2 capture can be read against
// them. See docs/BATTERY.md 10.
#include <Arduino.h>
#include <Wire.h>

#include "epd.h"
#include "InkplateBoard.h"
#include "log_utils.h"
#include "sleep_utils.h"
#include "version.h"
#include "wake.h"

#include "sensors/Bme688Driver.h"
#include "sensors/II2cBus.h"
#include "sensors/IClock.h"
#include "sensors/Pmsa003iDriver.h"
#include "sensors/Readings.h"
#include "sensors/Scd41Driver.h"
#include "sensors/SensorValidation.h"
#include "sensors/Shtc3Driver.h"

static InkplateBoard inkplateBoard;

static const uint8_t  kRotation = 0;
// docs/HARDWARE.md 8: the PM module's SET line goes to expander P1_3.
static const uint8_t  kSetPin = 11;
static const uint32_t kSleepSeconds = 10;
// The RTC alarm reaches the SoC on GPIO 39, which Soldered does not guarantee
// on this board. The timer is what brings it back if the alarm does not.
static const uint32_t kTimerBackstopSeconds = 15;
// A read to an address with nothing on it costs this much before it gives up,
// and a bench with three sensors missing pays it a dozen times. The core's
// default is 50 ms, but a failed read here measured nearer a second, so the
// bound is set explicitly and the effective value logged.
static const uint16_t kI2cTimeoutMs = 50;

static ArduinoClock   wallClock;
static ArduinoI2cBus  i2cBus;

static void setFanLine(bool high) { epdBoard().writeExpanderPin(kSetPin, high); }
static void logLine(int level, const char* line) { log((uint16_t)level, line); }

static Shtc3Driver    shtc3(i2cBus, wallClock);
static Scd41Driver    scd41(i2cBus, wallClock);
static Bme688Driver   bme(i2cBus, wallClock);
static Pmsa003iDriver pm(i2cBus, wallClock, setFanLine);

static SensorValidation validation(wallClock, i2cBus, Pmsa003iDriver::kAddress, shtc3, scd41,
                                   pm, bme, logLine);

// Every address that answers, wired or not. A part missing here is a cable,
// not a driver.
static void scanBus() {
    char found[80] = {0};
    size_t len = 0;
    int count = 0;
    for (uint8_t addr = 0x08; addr <= 0x77; ++addr) {
        if (!i2cBus.write(addr, nullptr, 0)) continue;
        ++count;
        if (len < sizeof(found) - 6)
            len += snprintf(found + len, sizeof(found) - len, " 0x%02X", addr);
    }
    logf(LOG_NOTICE, "i2c scan:%s (%d devices)", found, count);
}

void setup() {
    epdBegin(inkplateBoard);
    startBoard(kRotation);
    logWakeReason();
    // logWakeReason() clears the flag only when the alarm is what woke the
    // board. Waking on the timer with the alarm still pending would make the
    // next sleep return at once.
    epdBoard().rtcClearAlarmFlag();

    logf(LOG_NOTICE, "##### %s hardware validation #####", epdBoard().deviceName());
    logf(LOG_NOTICE, "Client version: %s", CLIENT_VERSION);
    logf(LOG_INFO, "battery voltage: %sv   panel %d C",
         String(epdBoard().readBattery(), 2).c_str(), epdBoard().readPanelTemperature());

    Wire.setTimeOut(kI2cTimeoutMs);
    logf(LOG_INFO, "i2c timeout %u ms", Wire.getTimeOut());

    scanBus();

    SensorValidation::Report report = validation.run((uint32_t)epdBoard().rtcGetEpoch());

    char json[640];
    if (readingsToJson(report.gathered, CLIENT_NAME, json, sizeof(json)))
        log(LOG_DEBUG, json);

    enableWakeOnTimer(kTimerBackstopSeconds);
    sleep_for(kSleepSeconds);
}

// Deep sleep ends the wake, so the board restarts in setup() and never
// arrives here.
void loop() {}
