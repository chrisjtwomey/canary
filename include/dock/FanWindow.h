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
// The window is the module's 30 s warm-up and a margin, counted back from
// the next post, so the reading the post carries is taken with the fan
// settled however long the gap between posts is.
class FanWindow {
public:
    explicit FanWindow(uint32_t leadMs) : lead_(leadMs) {}

    // untilPostMs is the time to the next post, 0 when it is due.
    bool shouldRun(uint32_t untilPostMs) const { return always_ || untilPostMs <= lead_; }

    uint32_t leadMs() const { return lead_; }

    // A lead of 0 keeps the fan running.
    void setLeadMs(uint32_t leadMs) {
        always_ = leadMs == 0;
        if (leadMs) lead_ = leadMs;
    }
    bool always() const { return always_; }

private:
    uint32_t lead_;
    bool     always_ = false;
};
