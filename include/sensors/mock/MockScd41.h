#pragma once
#include "../IScd41.h"
#include "EnvModel.h"
#include "LaggedValue.h"

// Behaves like the datasheet says an SCD41 does.
//   - periodic mode: new data every 5 s (30 s low-power), data_ready false in between
//   - single shot: ready 5 s after the command; the first shot after power-up
//     reads high and is meant to be discarded (the 2022 app note's rule)
//   - readMeasurement NACKs when nothing is ready, and clears the buffer
//   - commands other than read / data-ready / stop / pressure are refused
//     while periodic measurement runs; everything is refused for 500 ms
//     after stop
//   - self-heating rises from nothing after power-up toward +4 C, so with
//     the default 4 C offset a cold device reads about 4 C LOW and takes
//     roughly fifteen minutes to come right (design-in guide: allow 15 min
//     for thermal equilibration before judging the offset)
//   - every output trails the room by its response time: CO2 60 s, RH 90 s,
//     temperature 120 s
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
    bool getAutomaticSelfCalibration(bool& on) override;
    bool getTemperatureOffset(float& degC) override;
    bool setAutomaticSelfCalibration(bool on) override;
    // Fails unless the part has measured since power-up, as the datasheet
    // says the real one does; moves every later reading by the correction.
    bool performForcedRecalibration(uint32_t nowMs, uint16_t ppm, int16_t& correction) override;

    enum Mode { IDLE, PERIODIC, LOW_POWER_PERIODIC, SINGLE_SHOT, POWERED_DOWN };
    Mode mode() const { return mode_; }
    float temperatureOffset() const { return offsetC_; }
    bool selfCalibration() const { return asc_; }

    static const uint32_t kPeriodicMs   = 5000;
    static const uint32_t kLowPowerMs   = 30000;
    static const uint32_t kSingleShotMs = 5000;
    static const uint32_t kStopBusyMs   = 500;
    static const uint32_t kWakeMs       = 30;
    static const float    kSelfHeatingC;       // 4.0, the datasheet default offset
    static constexpr float kCo2TauS = 60.0f;
    static constexpr float kRhTauS = 90.0f;
    static constexpr float kTempTauS = 120.0f;
    // Not a datasheet figure: the enclosure's thermal mass. 300 s puts it
    // within 5% at the 15 minutes the design-in guide asks you to wait.
    static constexpr float kSelfHeatTauS = 300.0f;

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
    bool asc_ = true;
    bool measured_ = false;      // since power-up, which a recalibration needs
    float frcPpm_ = 0.0f;
    Scd41Data pending_{};
    LaggedValue co2_{kCo2TauS};
    LaggedValue temp_{kTempTauS};
    LaggedValue rh_{kRhTauS};
    LaggedValue selfHeat_{kSelfHeatTauS};
};
