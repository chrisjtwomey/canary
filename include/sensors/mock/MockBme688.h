#pragma once
#include "../IBme688.h"
#include "EnvModel.h"

// Behaves like the datasheet says a BME688 does in forced mode.
//   - a cycle takes the T/P/H conversion time (oversampling-dependent) plus
//     the heater duration; fetchData is false until then
//   - heat_stab is false on the first cycle after power-up, and always false
//     if the heater duration is under 30 ms or the target is outside
//     200–400 C (the plate needs 20–30 ms to reach temperature)
//   - the die runs ~1.5 C above the room (Bosch's LP-mode figure is 1.3),
//     so its RH reads low for the same absolute humidity
//   - gas resistance follows the room's VOC index and humidity, +-2 % noise
//   - IAQ is derived from gas resistance the way BSEC's output looks:
//     accuracy climbs 0 -> 1 -> 2 -> 3 over the first cycles, as BSEC's does
class MockBme688 : public IBme688 {
public:
    explicit MockBme688(EnvModel& room) : room_(room) {}

    bool begin(uint32_t nowMs) override;
    void setOversampling(uint8_t osT, uint8_t osP, uint8_t osH) override;
    void setHeaterProfile(uint16_t degC, uint16_t ms) override;
    bool startForced(uint32_t nowMs) override;
    uint32_t measurementMs() const override;
    bool fetchData(uint32_t nowMs, Bme688Data& out) override;
    uint8_t chipId() override { return 0x61; }

    uint32_t cycles() const { return cycles_; }

    static const uint32_t kHeaterSettleMs = 30;
    static const float    kSelfHeatingC;        // 1.5

private:
    EnvModel& room_;
    uint8_t osT_ = 2, osP_ = 16, osH_ = 1;
    uint16_t heaterC_ = 300, heaterMs_ = 100;
    bool running_ = false;
    uint32_t doneAtMs_ = 0;
    uint32_t cycles_ = 0;
};
