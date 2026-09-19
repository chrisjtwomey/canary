#include "net/Stamp.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>

static const char kZero[] = "{\"ts\":0,";
static const char kTaken[] = "{\"ts\":0,\"taken_ms\":";

size_t markUnstamped(const char* doc, uint32_t takenMs, char* out, size_t len) {
    const size_t zero = sizeof(kZero) - 1;
    if (strncmp(doc, kZero, zero) != 0) return 0;
    const int n = snprintf(out, len, "%s%lu,%s", kTaken, (unsigned long)takenMs, doc + zero);
    if (n < 0 || (size_t)n >= len) {
        if (len) out[0] = '\0';
        return 0;
    }
    return (size_t)n;
}

// The rest of the document after "taken_ms":N, or null.
static const char* afterTaken(const char* doc, uint32_t& takenMs) {
    const size_t taken = sizeof(kTaken) - 1;
    if (strncmp(doc, kTaken, taken) != 0) return nullptr;
    char* end = nullptr;
    const unsigned long ms = strtoul(doc + taken, &end, 10);
    if (end == doc + taken || *end != ',') return nullptr;
    takenMs = (uint32_t)ms;
    return end + 1;
}

bool unstampedAt(const char* doc, uint32_t& takenMs) {
    return afterTaken(doc, takenMs) != nullptr;
}

size_t stamp(const char* doc, const ServerClock& clock, char* out, size_t len) {
    uint32_t takenMs = 0;
    const char* rest = afterTaken(doc, takenMs);
    if (!rest || !clock.known()) return 0;
    const int n = snprintf(out, len, "{\"ts\":%lu,%s", (unsigned long)clock.epochAt(takenMs), rest);
    if (n < 0 || (size_t)n >= len) {
        if (len) out[0] = '\0';
        return 0;
    }
    return (size_t)n;
}

// Every document goes once from the oldest end to the newest. A stamped one
// is shorter than it was, so each push fits in the room its pop left.
uint32_t stampQueue(IBacklog& queue, const ServerClock& clock, char* buf, size_t bufLen,
                    char* out, size_t outLen) {
    if (!clock.known()) return 0;
    uint32_t stamped = 0;
    for (uint32_t n = queue.count(); n > 0; --n) {
        const size_t docLen = queue.peek(buf, bufLen);
        queue.pop();
        if (docLen == 0) continue;
        const size_t outN = stamp(buf, clock, out, outLen);
        if (outN) {
            queue.push(out, outN);
            ++stamped;
        } else {
            queue.push(buf, docLen);
        }
    }
    return stamped;
}
