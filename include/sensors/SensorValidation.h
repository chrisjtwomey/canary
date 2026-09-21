#pragma once
#include <cstdint>

#include "sensors/IBme688.h"
#include "sensors/IClock.h"
#include "sensors/II2cBus.h"
#include "sensors/IPmsa003i.h"
#include "sensors/IScd41.h"
#include "sensors/IShtc3.h"
#include "sensors/Readings.h"
#include "sensors/SensorSuite.h"

// One pass over the sensors that says whether the bench is wired and working:
// which parts answered, whether each reads sensibly running and in its
// low-power state (hardware/bom.md, per sensor), and one reading set from them all.
// It holds interfaces, so the same pass runs against the drivers on the board
// and against the fake parts in the host tests.
//
// It takes the bus as well as the four sensors because the PM module's sleep
// cannot be seen through IPmsa003i: the driver answers from its own enabled
// flag before it reaches the wire, so proving the fan stopped means asking
// the address directly.
class SensorValidation {
public:
    // The line and the level to log it at. epd's LOG_* numbering, which the
    // hardware main passes straight to log().
    typedef void (*LogFn)(int level, const char* line);

    static const int kLogError   = 1;
    static const int kLogWarning = 2;
    static const int kLogNotice  = 3;

    // SKIPPED is a check that could not be made, not one that passed.
    enum Outcome : uint8_t { SKIPPED, PASS, WARN, FAIL };

    struct SensorReport {
        bool    present;
        Outcome normal;
        Outcome lowPower;
    };

    struct Report {
        SensorReport shtc3, scd41, pm, bme688;
        Readings     gathered;
        bool         setLineWired;
        bool         pmAnsweredWithSetLow;
        uint8_t      warnings;
        uint8_t      failures;
        uint32_t     elapsedMs;
    };

    // `pmAddress` is the address the raw sleep probe reads; the caller passes
    // Pmsa003iDriver::kAddress rather than this class naming the part twice.
    SensorValidation(IClock& clock, II2cBus& bus, uint8_t pmAddress, IShtc3& shtc3,
                     IScd41& scd41, IPmsa003i& pm, IBme688& bme, LogFn logLine)
        : clock_(clock), bus_(bus), pmAddress_(pmAddress), shtc3_(shtc3), scd41_(scd41),
          pm_(pm), bme_(bme), suite_(clock, shtc3, scd41, pm, bme), logLine_(logLine) {}

    Report run(uint32_t epoch);

    // Against the ranges in hardware/bom.md, per sensor. WARN is outside the range
    // the sensor is specified for, FAIL is outside what it can report at all.
    static Outcome check(const Shtc3Data& d);
    static Outcome check(const Scd41Data& d);
    static Outcome check(const Bme688Data& d);
    static Outcome check(const PmData& d);

    static const char* outcomeName(Outcome o);

    // How long the module is given to fall silent after SET goes low.
    static const uint32_t kPmSetSettleMs = 1000;
    // Long enough that the next forced cycle is a fresh one, not the tail of
    // the last.
    static const uint32_t kBmeIdleGapMs = 1000;
    static const uint32_t kScd41ReadyPollMs    = 500;
    // One periodic interval plus the slack a single shot needs.
    static const uint32_t kScd41ReadyTimeoutMs = 7000;

    // The waits this sequence owes the datasheets, as SensorSuite states its
    // own rather than reaching into a driver for them.
    static const uint32_t kShtc3LowPowerMs  = 1;      // 0.8 ms max
    static const uint32_t kScd41StopBusyMs  = 500;    // busy after a stop
    static const uint32_t kScd41SingleShotMs = 5000;  // conversion
    static const uint32_t kPmStablePollMs   = 500;
    // The fan needs 30 s; past twice that it is not spinning up, it is broken.
    static const uint32_t kPmStableTimeoutMs = 60000;

private:
    void mark(const char* phase);
    void say(int level, const char* fmt, ...);
    Outcome record(Report& r, Outcome o);

    void probe(Report& r);
    void checkPmSetLine(Report& r);
    void checkShtc3(Report& r);
    void checkScd41(Report& r);
    void checkBme688(Report& r);
    void checkPmRunning(Report& r);
    void gather(Report& r, uint32_t epoch);
    void allToLowPower(const Report& r);

    bool waitForScd41Data();
    bool pmAnswers();
    bool runBmeCycle(Bme688Data& out);

    IClock&     clock_;
    II2cBus&    bus_;
    uint8_t     pmAddress_;
    IShtc3&     shtc3_;
    IScd41&     scd41_;
    IPmsa003i&  pm_;
    IBme688&    bme_;
    SensorSuite suite_;
    LogFn       logLine_;
};
