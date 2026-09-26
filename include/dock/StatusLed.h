#pragma once
#include <cmath>
#include <cstdint>

// The dock's status LED as a duty cycle, and nothing else. The caller reads
// dutyAt() and writes it to the LEDC channel, so the pattern is tested on
// the host.
//
// Each state but UPDATING shows a look the server can set: a pattern and the
// length of one cycle of it, or none, which passes the light to the next
// state that holds. The defaults give a heartbeat while the dock runs, so a
// dead dock and a running one do not look alike.
//
// Brightness is perceived brightness, mapped to duty through gamma 2.2, up
// to a cap in percent of full: 15 by default, set by eye on a breadboard with
// no resistor in line. A cap of 0 keeps the LED dark whatever the state. A
// fade moves through the light in equal steps, as many as the smoothness
// gives, or with none to see.
class StatusLed {
public:
    static const uint8_t  kResolutionBits = 14;
    static const uint16_t kMaxDuty = (1u << kResolutionBits) - 1;
    static const uint32_t kFrequencyHz = 1000;

    // The steps of light a fade takes at each stop of the smoothness, from 1:
    // 4, 8, 16, 32, 64, then 0, for no steps to see.
    static const uint8_t  kSmoothnessStops = 6;
    static const uint8_t  kDefaultSmoothness = 3;
    static constexpr uint8_t stepsAt(uint8_t stop) {
        return stop >= 1 && stop < kSmoothnessStops ? (uint8_t)(2u << stop) : 0;
    }
    // A flash is this long at the start of each cycle, or half the cycle
    // when that is shorter; a blip, the same but shorter.
    static const uint32_t kFlashMs = 150;
    static const uint32_t kBlipMs = 50;
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
    static constexpr float kUpdateDimmest = 0.25f;

    // Highest first: the dock shows the first that holds.
    enum State {
        BOOTING,         // connecting, or starting the sensors
        ERROR,           // anything wrong: the network, a post, a sensor, a setting
        POOR_AIR,        // a reading over its limit
        CALIBRATING,     // a sensor calibrating or recalibrating
        RUNNING,         // booted
        UPDATING,        // writing a new image; see progress()
        DARK,            // no state that holds has a look
    };
    // The states a look is set for: all before UPDATING.
    static const uint8_t kLooks = UPDATING;

    enum Pattern : uint8_t {
        OFF, SOLID, PULSE, FLASH,
        DOUBLE_FLASH, TRIPLE_FLASH, DOUBLE_PULSE, TRIPLE_PULSE,
        BLIP,    // a very short flash at the start of each cycle
        SWELL,   // fades up over a third, holds, and fades down over the last third
        RAMP,    // fades up over the cycle, then goes dark at once
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

    // A state's name as the server names its trigger; "updating" and "dark"
    // for the two it sets no look for.
    static const char* stateName(State s) {
        switch (s) {
            case BOOTING: return "booting";
            case ERROR: return "error";
            case POOR_AIR: return "poor_air_quality";
            case CALIBRATING: return "calibrating";
            case RUNNING: return "running";
            case UPDATING: return "updating";
            default: return "dark";
        }
    }

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

    // A stop of kStepsAt, from 1; one out of range changes nothing.
    void smoothness(uint8_t stop) {
        if (stop >= 1 && stop <= kSmoothnessStops) steps_ = stepsAt(stop);
    }
    // The steps of light a fade takes; 0 for none to see.
    uint8_t steps() const { return steps_; }

    // Unsigned arithmetic, so the millis() rollover only shifts the phase.
    uint16_t dutyAt(uint32_t nowMs) const {
        const uint32_t since = nowMs - startedMs_;
        if (state_ == UPDATING) {
            const uint32_t period =
                kUpdateSlowestMs - (kUpdateSlowestMs - kUpdateFastestMs) * progress_ / 1000;
            const float top = kUpdateDimmest + (1.0f - kUpdateDimmest) * progress_ / 1000.0f;
            return pulseDuty(since % period, period, top);
        }
        if (state_ == DARK) return 0;
        const uint32_t length = lengthMs_[state_];
        const uint32_t phase = since % length;
        const Pattern pattern = (Pattern)pattern_[state_];
        switch (pattern) {
            case SOLID: return peakDuty();
            case PULSE: return pulseDuty(phase, length);
            case FLASH: return phase < litMs(kFlashMs, length) ? peakDuty() : 0;
            case BLIP: return phase < litMs(kBlipMs, length) ? peakDuty() : 0;
            case SWELL: {
                const uint32_t third = length / 3;
                if (phase < third) return pulseDuty(phase, 2 * third);
                if (phase < length - third) return peakDuty();
                return pulseDuty(phase - (length - 2 * third), 2 * third);
            }
            case RAMP: return levelDuty((float)phase / length);
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

    // The full light, which is also the flash, the blip and the solid light.
    uint16_t peakDuty() const { return levelDuty(1.0f); }

    // `level`, 0 to 1 of the cap, on the nearest step of the smoothness, as
    // an LEDC duty.
    uint16_t levelDuty(float level) const {
        if (level < 0.0f) level = 0.0f;
        if (level > 1.0f) level = 1.0f;
        const uint8_t steps = steps_;
        if (steps > 1) level = (float)(int)(level * (steps - 1) + 0.5f) / (steps - 1);
        const float gamma = 2.2f;
        return (uint16_t)(kMaxDuty * std::pow(capPct_ / 100.0f * level, gamma) + 0.5f);
    }

    static const uint8_t kDefaultBrightnessPct = 15;

private:
    // A flash's lit time: `ms`, or half the cycle when that is shorter.
    static uint32_t litMs(uint32_t ms, uint32_t length) { return length / 2 < ms ? length / 2 : ms; }

    uint16_t pulseDuty(uint32_t phase, uint32_t periodMs, float top = 1.0f) const {
        const float turn = 2.0f * 3.14159265f * phase / periodMs;
        const float light = 0.5f * (1.0f - std::cos(turn));
        return levelDuty(top * light);
    }

    State    state_ = BOOTING;
    uint32_t startedMs_ = 0;
    uint16_t progress_ = 0;
    // The server's defaults, which dock_settings.py also holds.
    volatile uint8_t  pattern_[kLooks] = {PULSE, FLASH, DOUBLE_FLASH, SWELL, PULSE};
    volatile uint32_t lengthMs_[kLooks] = {500, 1000, 2000, 4000, 1000};
    volatile uint8_t capPct_ = kDefaultBrightnessPct;
    volatile uint8_t steps_ = stepsAt(kDefaultSmoothness);
};
