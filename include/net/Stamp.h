#pragma once
#include <cstddef>
#include <cstdint>

#include "net/Backlog.h"
#include "net/ServerClock.h"

// A reading taken before the dock knew the time, and the time put in later.
//
// Such a reading is queued as {"ts":0,"taken_ms":N,...}, with N the uptime it
// was taken at. It is never sent like that: once the server's clock arrives,
// stampQueue rewrites it as {"ts":<epoch>,...}. The documents are the
// readings JSON, whose first member is always "ts".

// `doc`, which must start {"ts":0, with the uptime it was taken at added.
// Returns the length written, or 0 when doc does not start so or out is too
// small.
size_t markUnstamped(const char* doc, uint32_t takenMs, char* out, size_t len);

// Whether `doc` is waiting for its time, and the uptime it was taken at.
bool unstampedAt(const char* doc, uint32_t& takenMs);

// `doc` with its time put in from `clock`. Returns the length written, or 0
// when doc is not waiting for its time, the clock is unknown, or out is too
// small.
size_t stamp(const char* doc, const ServerClock& clock, char* out, size_t len);

// Put the time into every queued reading waiting for it, keeping their
// order. `buf` and `out` each hold one document. A document too long for
// them is dropped, as the sender would drop it. Returns how many were
// stamped.
uint32_t stampQueue(IBacklog& queue, const ServerClock& clock, char* buf, size_t bufLen,
                    char* out, size_t outLen);
