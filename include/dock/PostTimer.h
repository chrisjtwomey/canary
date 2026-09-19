#pragma once
#include <cstdint>

// When the dock next takes a reading and posts it.
//
// The server says, as the seconds to its next slot on the wall clock, on
// every response. Without an answer the dock goes one interval on from the
// reading it last took, the interval being the gap the server gave between
// two slots. So a post that fails keeps the rhythm, and the first answer
// puts the dock back on the slots.
class PostTimer {
public:
    explicit PostTimer(uint32_t intervalMs) : interval_(intervalMs) {}

    // The next reading is `inMs` from now, whatever the server says.
    void postAt(uint32_t nowMs, uint32_t inMs) {
        at_ = nowMs + inMs;
        onSlot_ = false;
    }

    bool due(uint32_t nowMs) const { return (int32_t)(nowMs - at_) >= 0; }

    // 0 when the reading is due or late.
    uint32_t untilMs(uint32_t nowMs) const { return due(nowMs) ? 0 : at_ - nowMs; }

    // A reading was taken. The next is one interval on until the server
    // answers.
    void taken(uint32_t nowMs) {
        afterSlot_ = onSlot_;
        postAt(nowMs, interval_);
    }

    // The server's next slot is `seconds` away. The first answer after a
    // reading taken on a slot is the gap between two slots, so it becomes the
    // interval.
    void answered(uint32_t nowMs, uint32_t seconds) {
        if (!seconds) return;
        at_ = nowMs + seconds * 1000;
        onSlot_ = true;
        if (afterSlot_) interval_ = seconds * 1000;
        afterSlot_ = false;
    }

    uint32_t intervalMs() const { return interval_; }

private:
    uint32_t interval_;
    uint32_t at_ = 0;
    bool     onSlot_ = false;      // at_ came from the server
    bool     afterSlot_ = false;   // the last reading was taken on a slot
};
