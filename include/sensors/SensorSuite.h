#pragma once
#include <cstdint>

#include "sensors/IBme688.h"
#include "sensors/IClock.h"
#include "sensors/IPmsa003i.h"
#include "sensors/IScd41.h"
#include "sensors/IShtc3.h"
#include "sensors/Readings.h"
#include "sensors/SensorHealth.h"

// The four sensors as one thing to start and one thing to sample.
//
// It holds interfaces, so the same code drives the mocks and the real
// drivers; the choice is made once, where the suite is constructed. The
// sequence it runs — wake, measure, wait the datasheet time, read, sleep —
// is the same either way, which is the point: the mocks exercise the code
// that will run on the device, not a parallel copy of it.
//
// A sample takes roughly 150 ms of wall clock, nearly all of it the BME688
// heater. The dock samples once a slot, and ::delay() yields on ESP32, so
// WiFi keeps running.
class SensorSuite {
public:
    SensorSuite(IClock& clock, IShtc3& shtc3, IScd41& scd41, IPmsa003i& pm, IBme688& bme)
        : clock_(clock), shtc3_(shtc3), scd41_(scd41), pm_(pm), bme_(bme) {}

    // Start every sensor and leave the SCD41 measuring. True when all four
    // came up; the per-sensor flags say which did.
    bool begin();

    // Start again each sensor that did not start, or that has stopped giving
    // readings, when its retry is due. A restart waits as a start does: 3 s
    // for the PM module to boot, half a second for the SCD41.
    void restartFailed();

    // Whether each sensor is running: started, and still giving readings.
    bool shtc3Present()  const { return shtc3State_.running; }
    bool scd41Present()  const { return scd41State_.running; }
    bool pmPresent()     const { return pmState_.running; }
    bool bme688Present() const { return bmeState_.running; }

    // Starts tried by restartFailed(), whether or not they worked.
    uint32_t restarts() const { return restarts_; }

    // How the sensors are faring: the counts since start, the BME688's state
    // at the last sample, and the SCD41's settings as read at its start.
    SensorHealth health() const;

    // One reading set, stamped with `epoch`. Sensors that fail or are not
    // ready leave their `*Valid` flag false rather than filling in stale or
    // invented numbers.
    Readings sample(uint32_t epoch);

    // The SCD41's temperature offset and self-calibration, set at each start,
    // since the part keeps them only until a power cycle. A change while it
    // runs stops it for about half a second to set them. Until the first
    // call it keeps its own.
    void setScd41Options(float offsetC, bool selfCalibration);

    // SHTC3 low-power mode, from the next sample.
    void setShtc3LowPower(bool on) { shtc3LowPower_ = on; }

    enum class Recalibration { Done, Failed, NotReady };
    // A forced recalibration of the SCD41 to `ppm`, which stops it for about
    // a second. NotReady until it has measured for kFrcAfterMs since its
    // start; `correction` is set when Done.
    Recalibration recalibrateScd41(uint16_t ppm, int16_t& correction);

    // The PM fan. Low stops it and, on the Adafruit board, its 5 V charge
    // pump; readings are untrustworthy for 30 s after it restarts, which
    // sample() honours through IPmsa003i::stable().
    void setFanEnabled(bool on);

    // SCD41 power-up to idle, datasheet 30 ms max.
    static const uint32_t kScd41WakeMs = 30;
    // SHTC3 normal-mode conversion, datasheet 12.1 ms max.
    static const uint32_t kShtc3MeasureMs = 13;
    // SHTC3 low-power conversion, datasheet 0.8 ms max.
    static const uint32_t kShtc3LowPowerMs = 1;
    // The SCD41 takes no command for 500 ms after a stop.
    static const uint32_t kScd41StopMs = 500;
    // Datasheet 3.7.1: a forced recalibration wants 3 minutes of measuring.
    static const uint32_t kFrcAfterMs = 180000;
    // BME688 forced-mode profile: 300 C for 100 ms is Bosch's indoor VOC
    // example, and the plate needs 20-30 ms of that to reach temperature.
    static const uint16_t kBmeHeaterC = 300;
    static const uint16_t kBmeHeaterMs = 100;
    // Oversampling: 2x temperature, 16x pressure, 1x humidity (datasheet 3.5).
    static const uint8_t kBmeOsT = 2, kBmeOsP = 16, kBmeOsH = 1;
    // A PM frame read can land on a bus glitch; one retry covers it.
    static const int kPmReadAttempts = 2;

    // A running sensor that gives no reading in a sample that expected one has
    // stopped: unplugged, or back from a power cut without its settings. Not
    // within kStoppedAfterMs of its start or its last reading, so a sensor
    // still settling after a start is not taken for a stopped one.
    static const uint32_t kStoppedAfterMs = 15000;
    // A start that fails is tried again after this, then after twice the last
    // wait each time, up to kRetryMaxMs.
    static const uint32_t kRetryFirstMs = 30000;
    static const uint32_t kRetryMaxMs = 600000;

private:
    struct SensorState {
        bool     running = false;
        uint32_t lastReadingMs = 0;    // or the last start
        uint32_t retryAtMs = 0;
        uint32_t retryWaitMs = kRetryFirstMs;
    };
    typedef bool (SensorSuite::*StartFn)();

    bool startShtc3();
    bool startScd41();
    bool startPm();
    bool startBme688();
    bool stopScd41();
    void resumeScd41();
    void readScd41Settings();
    void started(SensorState& s, bool ok);
    void retry(SensorState& s, StartFn start);
    void track(SensorState& s, bool due, bool valid);

    void sampleShtc3(Readings& r);
    void sampleBme688(Readings& r);
    void sampleScd41(Readings& r);
    void samplePm(Readings& r);

    IClock&    clock_;
    IShtc3&    shtc3_;
    IScd41&    scd41_;
    IPmsa003i& pm_;
    IBme688&   bme_;

    SensorState shtc3State_;
    SensorState scd41State_;
    SensorState pmState_;
    SensorState bmeState_;
    uint32_t    restarts_ = 0;
    uint32_t    pmBadFrames_ = 0;
    // Written as samples and starts happen, read by health().
    bool        bmeSeen_ = false;
    bool        gasValid_ = false;
    bool        heatStable_ = false;
    bool        scd41Read_ = false;
    uint64_t    scd41Serial_ = 0;
    bool        ascKnown_ = false, asc_ = false;
    bool        offsetKnown_ = false;
    float       offsetC_ = 0.0f;
    bool        pressureKnown_ = false;
    uint32_t    pressurePa_ = 0;
    bool        pmSeen_ = false;
    uint8_t     pmVersion_ = 0, pmError_ = 0;
    uint16_t    shtc3Id_ = 0;
    bool        shtc3LowPower_ = false;
    bool        scd41OptionsSet_ = false;
    float       scd41OffsetC_ = 0.0f;
    bool        scd41Asc_ = true;
    uint32_t    scd41MeasuringSinceMs_ = 0;
};
