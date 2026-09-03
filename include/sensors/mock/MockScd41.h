#pragma once
#include "../IScd41.h"
#include "EnvModel.h"

// Behaves like the datasheet says an SCD41 does.
//   - periodic mode: new data every 5 s (30 s low-power), data_ready false in between
//   - single shot: ready 5 s after the command; the first shot after power-up
//     reads high and is meant to be discarded (the 2022 app note's rule)
//   - readMeasurement NACKs when nothing is ready, and clears the buffer
//   - commands other than read / data-ready / stop / pressure are refused
//     while periodic measurement runs; everything is refused for 500 ms
//     after stop
//   - temperature reads +4 C over the room until setTemperatureOffset is tuned
//   - CO2 scales with the ratio of true to assumed ambient pressure, so
//     setAmbientPressure from the BME688 matters
//   - +-10 ppm repeatability
class MockScd41 : public IScd41 {
public:
    explicit MockScd41(EnvModel& room) : room_(room) {}

    bool begin(uint32_t nowMs) override;
    bool startPeriodicMeasurement(uint32_t nowMs) override;
    bool startLowPowerPeriodicMeasurement(uint32_t nowMs) override;
    bool stopPeriodicMeasurement(uint32_t nowMs) override;
    bool measureSingleShot(uint32_t nowMs) override;
    bool getDataReadyStatus(uint32_t nowMs, bool& ready) override;
    bool readMeasurement(uint32_t nowMs, Scd41Data& out) override;
    bool setAmbientPressure(uint32_t pa) override;
    bool setTemperatureOffset(float degC) override;
    bool powerDown() override;
    bool wakeUp(uint32_t nowMs) override;
    bool getSerialNumber(uint64_t& serial) override;

    enum Mode { IDLE, PERIODIC, LOW_POWER_PERIODIC, SINGLE_SHOT, POWERED_DOWN };
    Mode mode() const { return mode_; }
    float temperatureOffset() const { return offsetC_; }

    static const uint32_t kPeriodicMs   = 5000;
    static const uint32_t kLowPowerMs   = 30000;
    static const uint32_t kSingleShotMs = 5000;
    static const uint32_t kStopBusyMs   = 500;
    static const uint32_t kWakeMs       = 30;
    static const float    kSelfHeatingC;       // 4.0, the datasheet default offset

private:
    void refresh(uint32_t nowMs);
    bool busy(uint32_t nowMs) const { return nowMs < busyUntilMs_; }

    EnvModel& room_;
    Mode mode_ = POWERED_DOWN;
    bool ready_ = false;
    bool firstShotPending_ = true;
    uint32_t nextDataMs_ = 0;
    uint32_t busyUntilMs_ = 0;
    uint32_t assumedPa_ = 101300;
    float offsetC_ = 4.0f;
    Scd41Data pending_{};
};
