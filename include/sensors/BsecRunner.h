#pragma once
#include <cstdint>
#include <mutex>

#include "sensors/IBme688.h"
#include "sensors/IBsec.h"
#include "sensors/IClock.h"
#include "sensors/Readings.h"

// A copy of BSEC's learned state, and what the board knows about it.
struct BsecState {
    uint8_t  blob[IBsec::kMaxState];
    uint32_t len;
    uint8_t  accuracy;     // the IAQ accuracy when it was taken, 0-3
    uint32_t savedEpoch;   // UTC seconds when it was taken; 0 before NTP set the clock
};

// Where the state waits between boots: NVS on the board.
class IBsecStateStore {
public:
    virtual ~IBsecStateStore() {}
    virtual bool load(BsecState& out) = 0;
    virtual bool save(const BsecState& state) = 0;
};

// BSEC over the BME688, run by a task of its own so the loop's downloads and
// draws cannot make a sample late. Each step() asks BSEC what it wants, runs
// the forced cycle it asks for, and keeps the result; the task then sleeps
// for the milliseconds step() returns. The loop reads through the methods
// marked "any task", which take the lock.
class BsecRunner {
public:
    typedef uint32_t (*EpochFn)();   // UTC seconds, or 0 before NTP has set the clock

    struct Status {
        bool     started;      // BSEC took its configuration, whether or not the sensor answers
        bool     running;      // BSEC started, and the sensor answering
        bool     restored;     // BSEC took a saved state, not starting from nothing
        uint8_t  accuracy;     // of the last index, 0-3
        uint32_t lateCalls;    // times BSEC said it was asked late
        uint32_t savedEpoch;   // the last save to the store this boot; 0 for none
    };

    BsecRunner(IBsec& bsec, IBme688& bme, IClock& clock, IBsecStateStore& store, EpochFn epoch)
        : bsec_(bsec), bme_(bme), clock_(clock), store_(store), epoch_(epoch) {}

    // Start the sensor and BSEC, from the stored state when there is one.
    // Runs before the task does. `stored` gets the state that was loaded, so
    // the loop can weigh it against the server's copy.
    bool begin(BsecState* stored = nullptr);
    uint32_t step();

    // Any task: the newest cycle, with BSEC's index when it has one, and the
    // clock reading it was taken at. False before the first.
    bool latest(Bme688Data& out, uint32_t& atMs) const;
    // Any task: start BSEC again from `state` at the next step.
    void restartWith(const BsecState& state);
    // Any task: the state as of the last copy. False before the first.
    bool current(BsecState& out) const;
    // Any task.
    Status status() const;

    // A copy of the state for the readings POST.
    static const uint32_t kCopyEveryMs = 60000;
    // As Bosch's BSEC2 example does, and at once when the accuracy first
    // reaches 3 in a boot.
    static const uint32_t kSaveEveryMs = 6 * 3600 * 1000UL;
    // Cycles in a row the sensor may miss before it is started again.
    static const uint8_t  kMissedLimit = 3;
    // How long to wait after BSEC refuses to start or to answer.
    static const uint32_t kRetryMs = 3000;

private:
    int64_t nowMs64();
    bool startBsec(const BsecState* state);
    void measure(const BsecRequest& request, int64_t nowNs);
    void applySettings(const BsecRequest& request);
    void copyState(uint32_t nowMs);
    void saveIfDue(uint32_t nowMs);
    uint32_t msUntilNextCall();

    IBsec&           bsec_;
    IBme688&         bme_;
    IClock&          clock_;
    IBsecStateStore& store_;
    EpochFn          epoch_;

    // The task's own.
    bool        started_ = false;
    int64_t     nextCallNs_ = 0;
    uint32_t    lastMs_ = 0;
    uint32_t    wraps_ = 0;
    uint8_t     missed_ = 0;
    bool        settingsApplied_ = false;
    BsecRequest applied_ = {};
    uint32_t    copiedAtMs_ = 0;
    uint32_t    savedAtMs_ = 0;
    bool        savedAtHigh_ = false;

    // Shared with the loop, under lock_.
    mutable std::mutex lock_;
    Bme688Data  latest_ = {};
    uint32_t    latestAtMs_ = 0;
    bool        haveLatest_ = false;
    BsecState   current_ = {};
    bool        haveCurrent_ = false;
    BsecState   pending_ = {};
    bool        restartPending_ = false;
    Status      status_ = {};
};

// The BME688 as SensorSuite sees it when BSEC drives the part: there is no
// cycle to start, BSEC chooses the settings, and the reading is the newest
// cycle BSEC ran.
class BsecBme688 : public IBme688 {
public:
    explicit BsecBme688(BsecRunner& runner) : runner_(runner) {}

    bool begin(uint32_t) override { return runner_.status().running; }
    void setOversampling(uint8_t, uint8_t, uint8_t) override {}
    void setHeaterProfile(uint16_t, uint16_t) override {}
    bool startForced(uint32_t) override { return true; }
    uint32_t measurementMs() const override { return 0; }
    bool fetchData(uint32_t nowMs, Bme688Data& out) override {
        uint32_t atMs = 0;
        return runner_.latest(out, atMs) && nowMs - atMs <= kFreshMs;
    }
    uint8_t chipId() override { return 0x61; }

    // Three of BSEC's 3 s cycles.
    static const uint32_t kFreshMs = 9000;

private:
    BsecRunner& runner_;
};
