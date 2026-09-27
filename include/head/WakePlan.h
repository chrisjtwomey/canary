#pragma once
#include <cstdint>

// When the head wakes next, and what for, in UTC seconds.
//
// The head keeps it in RTC memory through deep sleep, so it is a plain struct:
// all zeros is a real start, and nothing has to run to set it up. A real start
// fetches a page at once. Pure, so the head's timing is tested on the host.
struct WakePlan {
    uint32_t pageAt;   // the next page; 0 for at once
    uint32_t syncAt;   // the next sync; 0 for none, when the head syncs beside each page only
    int      step;     // fetches failed in a row
};

inline bool pageDue(const WakePlan& p, uint32_t now) { return now >= p.pageAt; }

inline bool syncDue(const WakePlan& p, uint32_t now) { return p.syncAt && now >= p.syncAt; }

inline bool wakeDue(const WakePlan& p, uint32_t now) { return pageDue(p, now) || syncDue(p, now); }

// waitSeconds is what the server sent; 0 means it sent nothing.
inline void pageFetched(WakePlan& p, uint32_t now, uint32_t waitSeconds, uint32_t fallbackSeconds) {
    p.step = 0;
    p.pageAt = now + (waitSeconds ? waitSeconds : fallbackSeconds);
}

// backoffSeconds maps the failure count to a wait. Returns the wait.
inline uint32_t pageFailed(WakePlan& p, uint32_t now, uint32_t (*backoffSeconds)(int)) {
    const uint32_t wait = backoffSeconds(++p.step);
    p.pageAt = now + wait;
    return wait;
}

// waitSeconds is the head's next sync, as the server sent it; 0 means none.
inline void synced(WakePlan& p, uint32_t now, uint32_t waitSeconds) {
    p.syncAt = waitSeconds ? now + waitSeconds : 0;
}

// The earlier of the next page and the next sync.
inline uint32_t nextWake(const WakePlan& p) {
    return p.syncAt && p.syncAt < p.pageAt ? p.syncAt : p.pageAt;
}

// 0 once `at` has come.
inline uint32_t secondsUntil(uint32_t at, uint32_t now) { return at > now ? at - now : 0; }
