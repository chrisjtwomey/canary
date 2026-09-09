#pragma once
#include <cstdint>

#include "IClock.h"
#include "II2cBus.h"
#include "IShtc3.h"

// Sensirion SHTC3 on I2C. The no-clock-stretch commands are the ones used:
// stretching the clock on an ESP32 blocks the bus for the whole conversion.
class Shtc3Driver : public IShtc3 {
public:
    Shtc3Driver(II2cBus& bus, IClock& clock, uint8_t addr = kAddress)
        : bus_(bus), clock_(clock), addr_(addr) {}

    bool begin(uint32_t nowMs) override;
    bool wakeup(uint32_t nowMs) override;
    bool sleep() override;
    bool measure(uint32_t nowMs, bool lowPower) override;
    bool read(uint32_t nowMs, Shtc3Data& out) override;
    uint16_t readId() override;

    bool asleep() const { return asleep_; }

    static const uint8_t kAddress = 0x70;

    static const uint16_t kCmdWakeup      = 0x3517;
    static const uint16_t kCmdSleep       = 0xB098;
    static const uint16_t kCmdSoftReset   = 0x805D;
    static const uint16_t kCmdReadId      = 0xEFC8;
    static const uint16_t kCmdMeasure     = 0x7866;   // normal, no stretch, T first
    static const uint16_t kCmdMeasureLp   = 0x609C;   // low power, no stretch, T first

    // The ID word carries the part number in these bits; the rest is silicon
    // revision and differs between units.
    static const uint16_t kIdMask = 0x083F;
    static const uint16_t kId     = 0x0807;

    static const uint32_t kNormalMs   = 13;   // 12.1 ms max, rounded up
    static const uint32_t kLowPowerMs = 1;    // 0.8 ms max
    // Wake-up and soft reset both complete in 240 us. One millisecond is the
    // finest wait IClock offers, and it is the smaller cost.
    static const uint32_t kSettleMs = 1;

private:
    II2cBus& bus_;
    IClock&  clock_;
    uint8_t  addr_;
    bool     asleep_ = true;
    bool     measuring_ = false;
    uint32_t readyAtMs_ = 0;
};
