#pragma once
#include <cstdint>

// When the PM module's fan runs.
//
// The fan is the dock's largest load and its largest heat source: about
// 200 mA of the sensors' 215 mA, which is a watt off the 5 V rail once the
// regulator's own loss is counted. A particle reading is only wanted when
// the dock posts, so the fan runs for a window before each post and stops
// after it.
//
// The window has to cover the module's 30 s warm-up and the sample that
// follows it, so that the reading the post carries is taken with the fan
// already settled.
class FanWindow {
public:
    FanWindow(uint32_t periodMs, uint32_t leadMs) : period_(periodMs), lead_(leadMs) {}

    // sinceMs is the time since the last post.
    bool shouldRun(uint32_t sinceMs) const { return sinceMs + lead_ >= period_; }

    // The share of each period the fan runs for, in percent.
    uint32_t dutyPercent() const {
        return lead_ >= period_ ? 100 : lead_ * 100 / period_;
    }

private:
    uint32_t period_;
    uint32_t lead_;
};
