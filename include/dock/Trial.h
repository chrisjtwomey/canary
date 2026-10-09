#pragma once

// Whether a freshly written image has failed often enough to give it up.
//
// The image is on trial until the server takes a batch from it. The dock is
// on mains, so three failures in a row, to join Wi-Fi, to get the server's
// time or to post, are the image's fault, and the one before it should come
// back. A success at any of those starts the count again, so failures of
// different kinds, apart, do not add up to a rollback.
class Trial {
public:
    static constexpr int kFailureLimit = 3;

    void begin(bool pending) {
        pending_ = pending;
        failures_ = 0;
    }

    bool pending() const { return pending_; }

    void succeeded() { failures_ = 0; }

    // True when the image is to be rolled back.
    bool failed() { return pending_ && ++failures_ >= kFailureLimit; }

    // The server took a batch: the image is kept.
    void passed() {
        pending_ = false;
        failures_ = 0;
    }

private:
    bool pending_ = false;
    int  failures_ = 0;
};
