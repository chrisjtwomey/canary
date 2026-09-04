#pragma once
#include <cstdint>

// When to fetch the next page. The server names the wait after every
// successful fetch; a failure backs off until one succeeds. Pure, so the
// awake loop's timing is tested on the host.
class RefreshTimer {
public:
    explicit RefreshTimer(uint32_t fallbackSeconds) : fallback_(fallbackSeconds) {}

    // Fetch on the first call, then whenever the wait has passed.
    bool due(uint32_t nowMs) const {
        return !armed_ || (int32_t)(nowMs - dueMs_) >= 0;
    }

    // waitSeconds is what the server sent; 0 means it sent nothing.
    void succeeded(uint32_t nowMs, uint32_t waitSeconds) {
        step_ = 0;
        arm(nowMs, waitSeconds ? waitSeconds : fallback_);
    }

    // backoffSeconds maps the failure count to a wait. Returns the wait.
    uint32_t failed(uint32_t nowMs, uint32_t (*backoffSeconds)(int)) {
        ++step_;
        uint32_t wait = backoffSeconds(step_);
        arm(nowMs, wait);
        return wait;
    }

    int step() const { return step_; }

private:
    void arm(uint32_t nowMs, uint32_t seconds) {
        dueMs_ = nowMs + seconds * 1000UL;
        armed_ = true;
    }

    uint32_t fallback_;
    uint32_t dueMs_ = 0;
    bool armed_ = false;
    int step_ = 0;
};
