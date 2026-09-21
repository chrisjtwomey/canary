// The bench routine: the dock's sensors instead of its awake loop.
//
// One pass over the bus and the four parts, then ten seconds and round again.
// It says which addresses answered, whether each sensor reads sensibly running
// and in its low-power state (hardware/bom.md, 2-5), and takes one reading set
// from them all. There is no network and no server, so what the serial log
// shows is the wiring and nothing else.
//
//   pio run -e dock-validate -t upload && pio device monitor -b 115200
//
// The phase markers carry milliseconds so a PPK2 capture can be read against
// them.
#include <Arduino.h>
#include <Wire.h>

#include "log_utils.h"
#include "version.h"

#include "sensors/Bme688Driver.h"
#include "sensors/II2cBus.h"
#include "sensors/IClock.h"
#include "sensors/Pmsa003iDriver.h"
#include "sensors/Readings.h"
#include "sensors/Scd41Driver.h"
#include "sensors/SensorValidation.h"
#include "sensors/Shtc3Driver.h"

// The dock's pins, as src/dock/main.cpp drives them. The PM module's SET line
// is a pin of the processor here, not an expander bit.
static const uint8_t kSdaPin   = 8;
static const uint8_t kSclPin   = 9;
static const uint8_t kPmSetPin = 7;

// Long enough to plug a part back in and watch the next pass find it.
static const uint32_t kPassIntervalMs = 10000;

static ArduinoClock  wallClock;
static ArduinoI2cBus i2cBus;

static void setFanLine(bool high) { digitalWrite(kPmSetPin, high ? HIGH : LOW); }
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
    char   found[80] = {0};
    size_t len       = 0;
    int    count     = 0;
    for (uint8_t addr = 0x08; addr <= 0x77; ++addr) {
        if (!i2cBus.write(addr, nullptr, 0)) continue;
        ++count;
        if (len < sizeof(found) - 6)
            len += snprintf(found + len, sizeof(found) - len, " 0x%02X", addr);
    }
    logf(LOG_NOTICE, "i2c scan:%s (%d devices)", found, count);
}

static void pass() {
    scanBus();
    // This board has no clock of its own and this build has no network to ask,
    // so a reading is stamped with seconds since boot. The suite needs a
    // timestamp, not the time of day.
    SensorValidation::Report report = validation.run(millis() / 1000);

    char json[640];
    if (readingsToJson(report.gathered, CLIENT_NAME, json, sizeof(json))) log(LOG_DEBUG, json);
}

void setup() {
    Serial.begin(115200);
    // The port exists only once the host opens it, and the first pass is the
    // one worth reading, so wait a little for it rather than print into nothing.
    for (uint32_t since = millis(); !Serial && millis() - since < 3000;) delay(10);

    logf(LOG_NOTICE, "##### %s hardware validation #####", CLIENT_NAME);
    logf(LOG_NOTICE, "Client version: %s", CLIENT_VERSION);

    pinMode(kPmSetPin, OUTPUT);
    digitalWrite(kPmSetPin, LOW);   // the fan stays off until the suite starts it
    Wire.begin(kSdaPin, kSclPin);
    Wire.setClock(100000);          // hardware/bom.md, the I2C bus: 100 kHz, and nothing cut
    // A bench with three sensors missing pays the timeout a dozen times, so the
    // effective value is logged.
    Wire.setTimeOut(ArduinoI2cBus::kTimeoutMs);
    logf(LOG_INFO, "i2c timeout %u ms; SDA IO%u, SCL IO%u, PM fan SET IO%u", Wire.getTimeOut(),
         (unsigned)kSdaPin, (unsigned)kSclPin, (unsigned)kPmSetPin);

    pass();
}

// The serial port is on this board's own USB, which a deep sleep would drop
// mid-bench, so the passes are spaced by a wait and the board stays up.
void loop() {
    delay(kPassIntervalMs);
    pass();
}
