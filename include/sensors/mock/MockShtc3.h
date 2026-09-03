#pragma once
#include "../IShtc3.h"
#include "EnvModel.h"

// Behaves like the datasheet says an SHTC3 does: 12.1 ms per normal
// measurement, 0.8 ms in low-power mode, NACKs when asleep, +-0.1 C /
// +-0.1 %RH repeatability (0.4 / 0.4 in low-power mode). It reads the room
// exactly: this is the reference sensor.
class MockShtc3 : public IShtc3 {
public:
    explicit MockShtc3(EnvModel& room) : room_(room) {}

    bool begin(uint32_t nowMs) override;
    bool wakeup(uint32_t nowMs) override;
    bool sleep() override;
    bool measure(uint32_t nowMs, bool lowPower) override;
    bool read(uint32_t nowMs, Shtc3Data& out) override;
    uint16_t readId() override { return 0x0887; }

    bool asleep() const { return asleep_; }

    static const uint32_t kNormalMs   = 13;   // 12.1 ms max, rounded up
    static const uint32_t kLowPowerMs = 1;    // 0.8 ms max

private:
    EnvModel& room_;
    bool asleep_ = true;
    bool measuring_ = false;
    bool lowPower_ = false;
    uint32_t readyAtMs_ = 0;
    uint32_t wokeAtMs_ = 0;
};
