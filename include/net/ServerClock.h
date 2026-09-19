#pragma once
#include <cstdint>

// The server's time, held as an offset from the board's uptime.
//
// The dock has no clock of its own and needs none: the server owns the
// schedule and stores the readings, so taking its time makes the two agree.
// Every response carries it, and each one moves the offset. Nothing here is
// ever set as a clock, so a correction cannot make timestamps run backwards
// for a reading already taken.
class ServerClock {
public:
    // The server said `epoch` in a response received at `atMs` of uptime.
    void sync(uint32_t epoch, uint32_t atMs) {
        if (!epoch) return;
        epoch_ = epoch;
        atMs_ = atMs;
    }

    bool known() const { return epoch_ != 0; }

    // UTC seconds at `ms` of uptime, before or after the last sync; 0 while
    // unknown. Right within 24 days of the sync either way, which a board
    // that syncs on every post never leaves.
    uint32_t epochAt(uint32_t ms) const {
        if (!known()) return 0;
        const int64_t delta = (int32_t)(ms - atMs_);
        const int64_t seconds = delta >= 0 ? delta / 1000 : -((-delta + 999) / 1000);
        return (uint32_t)((int64_t)epoch_ + seconds);
    }

private:
    uint32_t epoch_ = 0;
    uint32_t atMs_ = 0;
};
