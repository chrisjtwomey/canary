#pragma once

// What the head does once the server has answered a fetch.
//
// It draws the page, or the version notice when the two ends cannot work
// together. Then, whichever it drew, it records the success and takes any
// update on offer. The notice must reach the update: the server pulls the
// display to firmware matching its own version, that firmware is what clears
// the notice, and the dock's wall covers the head's USB-C socket.
struct AfterFetchSteps {
    bool (*drawPage)();
    bool (*drawVersionNotice)();
    void (*succeeded)();
    void (*takeOffer)();
};

// False when nothing could be drawn, which the caller counts as a failure.
inline bool afterFetch(bool compatible, const AfterFetchSteps& steps) {
    const bool drawn = compatible ? steps.drawPage() : steps.drawVersionNotice();
    if (!drawn) return false;
    steps.succeeded();
    steps.takeOffer();
    return true;
}
