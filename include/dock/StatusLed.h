#pragma once
#include <cmath>
#include <cstdint>

// The dock's status LED as a duty cycle, and nothing else. The caller reads
// dutyAt() and writes it to the LEDC channel, so the pattern is tested on
// the host.
//
// The LED is never dark for long: a slow pulse is the heartbeat, so a dead
// dock and a well one do not look alike.
//
// Brightness is perceived brightness, mapped to duty through gamma 2.2. The
// cap was set by eye on a breadboard with no resistor in line; with the 1 kOhm
// fitted it must be set again.
class StatusLed {
public:
    static const uint8_t  kResolutionBits = 14;
    static const uint16_t kMaxDuty = (1u << kResolutionBits) - 1;
    static const uint32_t kFrequencyHz = 1000;

    // A pulse is 16 equal steps of light, spaced in time along a sine. The
    // dock starts at 120 pulses a minute and settles to 60.
    static const uint8_t  kSteps = 16;
    static const uint32_t kFastPulseMs = 500;
    static const uint32_t kSlowPulseMs = 1000;

    // Trouble is three flashes filling the first second, then five steady.
    static const uint8_t  kTroubleFlashes = 3;
    static const uint32_t kTroubleFlashMs = 166;
    static const uint32_t kTroubleCycleMs = 6000;

    enum State {
        STARTING,   // connecting, or starting the sensors
        WELL,       // reading and posting, with everything answering
        TROUBLE,    // no network, a post the server would not take, a dead sensor
    };

    // Changing the state starts its pattern; repeating the current one does not.
    void state(State wanted, uint32_t nowMs) {
        if (wanted == state_) return;
        state_ = wanted;
        startedMs_ = nowMs;
    }

    State state() const { return state_; }

    // Unsigned arithmetic, so the millis() rollover only shifts the phase.
    uint16_t dutyAt(uint32_t nowMs) const {
        const uint32_t since = nowMs - startedMs_;
        switch (state_) {
            case STARTING: return pulseDuty(since % kFastPulseMs, kFastPulseMs);
            case WELL:     return pulseDuty(since % kSlowPulseMs, kSlowPulseMs);
            default:       return troubleDuty(since % kTroubleCycleMs);
        }
    }

    // The brightest step, which is also the flash and the steady glow.
    static uint16_t peakDuty() { return stepDuty(kSteps - 1); }

private:
    // Perceived brightness of step/15 of the cap, as an LEDC duty.
    static uint16_t stepDuty(uint8_t step) {
        const float cap = 0.15f;     // of full brightness, by eye
        const float gamma = 2.2f;
        const float level = cap * step / (kSteps - 1);
        return (uint16_t)(kMaxDuty * std::pow(level, gamma) + 0.5f);
    }

    static uint16_t pulseDuty(uint32_t phase, uint32_t periodMs) {
        const float turn = 2.0f * 3.14159265f * phase / periodMs;
        const float light = 0.5f * (1.0f - std::cos(turn));
        return stepDuty((uint8_t)((kSteps - 1) * light + 0.5f));
    }

    static uint16_t troubleDuty(uint32_t phase) {
        const uint32_t flashing = kTroubleFlashes * 2u * kTroubleFlashMs;
        if (phase < flashing && (phase / kTroubleFlashMs) % 2) return 0;
        return peakDuty();
    }

    State    state_ = STARTING;
    uint32_t startedMs_ = 0;
};
