#pragma once
#include "../IPmsa003i.h"
#include "EnvModel.h"
#include "LaggedValue.h"

// Behaves like the datasheet says a PMSA003I does.
//   - no answer for 3 s after power or wake (the library waits 3 s before begin)
//   - readings unstable for 30 s after the fan starts: they ramp up from zero
//   - a new frame every 2.3 s; reads in between return the same bytes
//   - one read in kChecksumFailEvery has a corrupt checksum (a real bus
//     glitch rate is unknown; this forces the retry path to exist)
//   - SET low: no frames at all
//   - CF=1 values sit above the atmospheric ones once concentrations rise
class MockPmsa003i : public IPmsa003i {
public:
    explicit MockPmsa003i(EnvModel& room) : room_(room) {}

    bool begin(uint32_t nowMs) override;
    void setEnabled(bool on, uint32_t nowMs) override;
    bool readFrame(uint32_t nowMs, uint8_t out[32]) override;
    bool stable(uint32_t nowMs) const override;
    // The simulated line is always connected; SET low really does stop it.
    bool setLineWired() const override { return true; }

    bool enabled() const { return enabled_; }

    static const uint32_t kBootMs          = 3000;
    static const uint32_t kWarmupMs        = 30000;
    static const uint32_t kFrameIntervalMs = 2300;
    static const uint32_t kChecksumFailEvery = 200;
    // "Total response time <=10 s" to settle, so about 4 s per tau63. This is
    // the optics answering a change in concentration; the 30 s above is the
    // fan reaching speed, and both apply.
    static constexpr float kConcentrationTauS = 4.0f;

private:
    void buildFrame(uint32_t nowMs);
    static void put16(uint8_t* p, uint16_t v) { p[0] = v >> 8; p[1] = v & 0xFF; }

    EnvModel& room_;
    bool enabled_ = false;
    uint32_t enabledAtMs_ = 0;
    uint32_t frameAtMs_ = 0;
    uint32_t reads_ = 0;
    uint8_t frame_[32] = {0};
    bool haveFrame_ = false;
    LaggedValue pm25_{kConcentrationTauS};
};
