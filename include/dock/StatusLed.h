#pragma once
#include <cmath>
#include <cstdint>

// The dock's status LED as a duty cycle, and nothing else. The caller reads
// dutyAt() and writes it to the LEDC channel, so the pattern is tested on
// the host.
//
// Each state but UPDATING shows a look the server can set: a pattern and the
// length of one cycle of it, or none, which passes the light to the next
// state that holds. The defaults give a heartbeat while the dock works, so a
// dead dock and a well one do not look alike.
//
// Brightness is perceived brightness, mapped to duty through gamma 2.2, up
// to a cap in percent of full: 15 by default, set by eye on a breadboard with
// no resistor in line. A cap of 0 keeps the LED dark whatever the state.
class StatusLed {
public:
    static const uint8_t  kResolutionBits = 14;
    static const uint16_t kMaxDuty = (1u << kResolutionBits) - 1;
    static const uint32_t kFrequencyHz = 1000;

    // A pulse is 16 equal steps of light, spaced in time along a sine.
    static const uint8_t  kSteps = 16;
    // A flash is this long at the start of each cycle, or half the cycle
    // when that is shorter.
    static const uint32_t kFlashMs = 150;
    // Each flash or quick pulse of a double or a triple: a flash lights for
    // kFlashMs of it. The rest of the cycle is dark, and is at least as long.
    static const uint32_t kGroupStepMs = 300;
    static const uint32_t kMinLengthMs = 250;
    static const uint32_t kMaxLengthMs = 10000;

    // Updating starts as a pulse a second at a quarter of the light, and
    // quickens and brightens with the image written, to four pulses a second
    // at full light.
    static const uint32_t kUpdateSlowestMs = 1000;
    static const uint32_t kUpdateFastestMs = 250;
    static const uint8_t  kUpdateDimmestStep = 4;

    // Highest first: the dock shows the first that holds.
    enum State {
        STARTING,        // connecting, or starting the sensors
        NO_WIFI,         // started, and off the network
        POST_FAILED,     // the last post did not reach the server, or it refused it
        SENSOR_MISSING,  // a sensor does not answer
        WELL,            // reading and posting, with everything answering
        UPDATING,        // writing a new image; see progress()
        DARK,            // no state that holds has a look
    };
    // The states a look is set for: all before UPDATING.
    static const uint8_t kLooks = UPDATING;

    enum Pattern : uint8_t {
        OFF, SOLID, PULSE, FLASH,
        DOUBLE_FLASH, TRIPLE_FLASH, DOUBLE_PULSE, TRIPLE_PULSE,
        kPatterns,
        NONE = 0xFF,
    };

    // How many flashes or quick pulses a double or a triple has; 0 for the rest.
    static constexpr uint8_t groupOf(Pattern p) {
        return p == DOUBLE_FLASH || p == DOUBLE_PULSE ? 2
             : p == TRIPLE_FLASH || p == TRIPLE_PULSE ? 3 : 0;
    }

    // The shortest cycle a pattern can have: a double's or a triple's group
    // and a dark gap of one step.
    static constexpr uint32_t minLengthMs(Pattern p) {
        return groupOf(p) ? (groupOf(p) + 1u) * kGroupStepMs : kMinLengthMs;
    }

    // A set of states, as show() takes them.
    static constexpr uint8_t flag(State s) { return (uint8_t)(1u << s); }

    // Shows the first state in `holding` that has a look, UPDATING before
    // the rest; with none, the light is dark.
    void show(uint8_t holding, uint32_t nowMs) {
        State wanted = DARK;
        if (holding & flag(UPDATING)) {
            wanted = UPDATING;
        } else {
            for (uint8_t s = 0; s < kLooks; ++s) {
                if ((holding & flag((State)s)) && pattern_[s] != NONE) {
                    wanted = (State)s;
                    break;
                }
            }
        }
        state(wanted, nowMs);
    }

    // Changing the state starts its pattern; repeating the current one does not.
    void state(State wanted, uint32_t nowMs) {
        if (wanted == state_) return;
        state_ = wanted;
        startedMs_ = nowMs;
    }

    State state() const { return state_; }

    // The look of state `s`: a pattern, and the length of one cycle of it.
    // NONE leaves the state without one, whatever the length. A state that
    // takes no look, a pattern out of range or a length of 0 changes nothing.
    // The LED task reads it while the loop sets it; a torn read shows one
    // step of a wrong look.
    void look(State s, Pattern pattern, uint32_t lengthMs) {
        if (s >= kLooks) return;
        if (pattern == NONE) {
            pattern_[s] = NONE;
            return;
        }
        if (pattern >= kPatterns || lengthMs == 0) return;
        pattern_[s] = pattern;
        lengthMs_[s] = lengthMs;
    }

    Pattern pattern(State s) const {
        return s < kLooks ? (Pattern)pattern_[s] : s == UPDATING ? PULSE : OFF;
    }
    uint32_t lengthMs(State s) const { return s < kLooks ? lengthMs_[s] : 0; }

    // The cap, in percent of full brightness; above 100 is 100. The LED task
    // reads it, so it is one byte.
    void brightness(uint8_t pct) { capPct_ = pct > 100 ? 100 : pct; }
    uint8_t brightness() const { return capPct_; }

    // How much of the image is written, in thousandths.
    void progress(uint16_t permille) { progress_ = permille > 1000 ? 1000 : permille; }

    // Unsigned arithmetic, so the millis() rollover only shifts the phase.
    uint16_t dutyAt(uint32_t nowMs) const {
        const uint32_t since = nowMs - startedMs_;
        if (state_ == UPDATING) {
            const uint32_t period =
                kUpdateSlowestMs - (kUpdateSlowestMs - kUpdateFastestMs) * progress_ / 1000;
            const uint8_t top = (uint8_t)(kUpdateDimmestStep +
                ((kSteps - 1 - kUpdateDimmestStep) * progress_ + 500) / 1000);
            return pulseDuty(since % period, period, top);
        }
        if (state_ == DARK) return 0;
        const uint32_t length = lengthMs_[state_];
        const uint32_t phase = since % length;
        const Pattern pattern = (Pattern)pattern_[state_];
        switch (pattern) {
            case SOLID: return peakDuty();
            case PULSE: return pulseDuty(phase, length);
            case FLASH: {
                const uint32_t lit = length / 2 < kFlashMs ? length / 2 : kFlashMs;
                return phase < lit ? peakDuty() : 0;
            }
            case DOUBLE_FLASH:
            case TRIPLE_FLASH:
            case DOUBLE_PULSE:
            case TRIPLE_PULSE: {
                if (phase >= groupOf(pattern) * kGroupStepMs) return 0;
                const uint32_t step = phase % kGroupStepMs;
                if (pattern == DOUBLE_FLASH || pattern == TRIPLE_FLASH) {
                    return step < kFlashMs ? peakDuty() : 0;
                }
                return pulseDuty(step, kGroupStepMs);
            }
            default: return 0;
        }
    }

    // The brightest step, which is also the flash and the solid light.
    uint16_t peakDuty() const { return stepDuty(kSteps - 1); }

    static const uint8_t kDefaultBrightnessPct = 15;

private:
    // Perceived brightness of step/15 of the cap, as an LEDC duty.
    uint16_t stepDuty(uint8_t step) const {
        const float cap = capPct_ / 100.0f;
        const float gamma = 2.2f;
        const float level = cap * step / (kSteps - 1);
        return (uint16_t)(kMaxDuty * std::pow(level, gamma) + 0.5f);
    }

    uint16_t pulseDuty(uint32_t phase, uint32_t periodMs, uint8_t top = kSteps - 1) const {
        const float turn = 2.0f * 3.14159265f * phase / periodMs;
        const float light = 0.5f * (1.0f - std::cos(turn));
        return stepDuty((uint8_t)(top * light + 0.5f));
    }

    State    state_ = STARTING;
    uint32_t startedMs_ = 0;
    uint16_t progress_ = 0;
    // The server's defaults, which dock_settings.py also holds.
    volatile uint8_t  pattern_[kLooks] = {PULSE, FLASH, FLASH, FLASH, PULSE};
    volatile uint32_t lengthMs_[kLooks] = {500, 1000, 2000, 3000, 1000};
    volatile uint8_t capPct_ = kDefaultBrightnessPct;
};
