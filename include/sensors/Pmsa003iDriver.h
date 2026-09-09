#pragma once
#include <cstdint>

#include "IClock.h"
#include "II2cBus.h"
#include "IPmsa003i.h"

// Plantower PMSA003I on the Adafruit breakout. There are no commands: the
// host reads the 32-byte frame the module keeps updated, and the SET pin
// starts and stops the fan.
class Pmsa003iDriver : public IPmsa003i {
public:
    // SET comes from the Inkplate's IO expander on this board, so the driver
    // takes a function rather than a pin number. A null function says the
    // line is not wired: the breakout's pull-up then holds the fan on for as
    // long as the board has power, and setEnabled() cannot change that.
    typedef void (*SetLineFn)(bool high);

    Pmsa003iDriver(II2cBus& bus, IClock& clock, SetLineFn setLine = nullptr,
                   uint8_t addr = kAddress)
        : bus_(bus), clock_(clock), setLine_(setLine), addr_(addr),
          enabled_(setLine == nullptr) {}

    bool begin(uint32_t nowMs) override;
    void setEnabled(bool on, uint32_t nowMs) override;
    bool readFrame(uint32_t nowMs, uint8_t out[32]) override;
    bool stable(uint32_t nowMs) const override;

    bool enabled() const { return enabled_; }
    bool setLineWired() const { return setLine_ != nullptr; }

    static const uint8_t kAddress = 0x12;

    static const uint32_t kBootMs   = 3000;
    static const uint32_t kWarmupMs = 30000;
    // The module has no ID register, so a frame that parses is the only proof
    // it is there. A bus glitch corrupts one occasionally; three tries a tenth
    // of a second apart separate that from an absent sensor.
    static const int      kBeginAttempts = 3;
    static const uint32_t kRetryMs = 100;

private:
    II2cBus&  bus_;
    IClock&   clock_;
    SetLineFn setLine_;
    uint8_t   addr_;
    bool      enabled_;
    uint32_t  enabledAtMs_ = 0;
};
