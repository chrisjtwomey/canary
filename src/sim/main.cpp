// Runs the client's sensor loop on the host and prints what it reads.
//
// Same EnvModel, same mocks, same SensorSuite as the firmware — everything
// but Arduino.h. Use it to watch a simulated day go by in a second, or to
// check the JSON the device will POST, without a board or a sensor.
//
//   pio run -e sim && .pio/build/sim/program --help
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include "sensors/Readings.h"
#include "sensors/SensorSuite.h"
#include "sensors/mock/EnvModel.h"
#include "sensors/mock/MockBme688.h"
#include "sensors/mock/MockPmsa003i.h"
#include "sensors/mock/MockScd41.h"
#include "sensors/mock/MockShtc3.h"

namespace {

// 2025-09-03 00:00 UTC. Only the time of day matters to the room.
const uint32_t kMidnight = 1756857600;

struct Options {
    float startHour = 6.0f;
    float hours = 24.0f;
    uint32_t intervalS = 300;
    float speed = 0.0f;     // simulated seconds per real second; 0 = no waiting
    bool json = false;
    uint32_t seed = 7;
};

// A clock the simulation drives. waitMs moves it, so the sensors see the
// datasheet timings pass exactly as they do on the device.
class SimClock : public IClock {
public:
    uint32_t now = 0;
    uint32_t millis() const override { return now; }
    void waitMs(uint32_t ms) override { now += ms; }
    void advance(uint32_t ms) { now += ms; }
};

void usage() {
    printf(
        "Run the environment monitor's sensor loop against the simulated room.\n\n"
        "  --start HH:MM   time of day to start at        (default 06:00)\n"
        "  --hours N       hours of room time to simulate (default 24)\n"
        "  --interval N    seconds between samples        (default 300)\n"
        "  --speed N       simulated seconds per real second, 0 = as fast as\n"
        "                  possible                       (default 0)\n"
        "  --json          print the JSON the device POSTs, not a table\n"
        "  --seed N        room seed                      (default 7)\n"
        "  --help\n\n"
        "Examples:\n"
        "  program                        a whole day, five-minute samples, instantly\n"
        "  program --interval 5 --hours 1 every 5 s for an hour; shows the fan warm-up\n"
        "  program --speed 60             watch it unfold, a minute a second\n"
        "  program --json --hours 0.1     check the posted wire format\n");
}

bool parseHour(const char* s, float& out) {
    int h = 0, m = 0;
    if (sscanf(s, "%d:%d", &h, &m) != 2 || h < 0 || h > 23 || m < 0 || m > 59) return false;
    out = h + m / 60.0f;
    return true;
}

bool parse(int argc, char** argv, Options& o) {
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        const char* next = (i + 1 < argc) ? argv[i + 1] : nullptr;
        if (a == "--help" || a == "-h") { usage(); exit(0); }
        else if (a == "--json") o.json = true;
        else if (!next) { fprintf(stderr, "%s needs a value\n", a.c_str()); return false; }
        else if (a == "--start") { if (!parseHour(next, o.startHour)) { fprintf(stderr, "--start wants HH:MM\n"); return false; } ++i; }
        else if (a == "--hours") { o.hours = atof(next); ++i; }
        else if (a == "--interval") { o.intervalS = (uint32_t)atoi(next); ++i; }
        else if (a == "--speed") { o.speed = atof(next); ++i; }
        else if (a == "--seed") { o.seed = (uint32_t)atoi(next); ++i; }
        else { fprintf(stderr, "unknown option %s\n", a.c_str()); usage(); return false; }
    }
    if (o.intervalS == 0) { fprintf(stderr, "--interval must be at least 1\n"); return false; }
    return true;
}

void printHeader() {
    printf("  time   temp    rh    co2   pm2.5   iaq  gas kohm  press  sensors\n");
    printf("  ─────  ─────  ────  ─────  ─────  ────  ────────  ──────  ────────\n");
}

void printRow(const Readings& r) {
    char clock[6];
    snprintf(clock, sizeof(clock), "%02u:%02u", (r.ts % 86400) / 3600, (r.ts % 3600) / 60);

    char temp[8] = "    -", rh[7] = "   -", co2[8] = "    -";
    char pm[8] = "    -", iaq[7] = "   -", gas[10] = "       -", press[8] = "     -";
    if (r.shtc3Valid) {
        snprintf(temp, sizeof(temp), "%5.1f", r.shtc3.tempC);
        snprintf(rh, sizeof(rh), "%4.0f", r.shtc3.rhPct);
    }
    if (r.scd41Valid) snprintf(co2, sizeof(co2), "%5u", r.scd41.co2Ppm);
    if (r.pmValid) snprintf(pm, sizeof(pm), "%5u", r.pm.pm2_5);
    if (r.bme688Valid) {
        snprintf(iaq, sizeof(iaq), "%4.0f", r.bme688.iaq);
        snprintf(gas, sizeof(gas), "%8.1f", r.bme688.gasOhm / 1000.0f);
        snprintf(press, sizeof(press), "%6.1f", r.bme688.pressureHpa);
    }

    printf("  %s  %s  %s  %s  %s  %s  %s  %s  %c%c%c%c\n",
           clock, temp, rh, co2, pm, iaq, gas, press,
           r.shtc3Valid ? 'T' : '.', r.scd41Valid ? 'C' : '.',
           r.pmValid ? 'P' : '.', r.bme688Valid ? 'G' : '.');
}

}  // namespace

int main(int argc, char** argv) {
    Options o;
    if (!parse(argc, argv, o)) return 2;

    EnvModel     room(o.seed);
    SimClock     clk;
    MockShtc3    shtc3(room);
    MockScd41    scd41(room);
    MockPmsa003i pm(room);
    MockBme688   bme(room);
    SensorSuite  sensors(clk, shtc3, scd41, pm, bme);

    const uint32_t startEpoch = kMidnight + (uint32_t)(o.startHour * 3600.0f);
    const uint32_t endEpoch = startEpoch + (uint32_t)(o.hours * 3600.0f);
    room.reset(startEpoch);

    if (!sensors.begin()) {
        fprintf(stderr, "sensor start incomplete: shtc3=%d scd41=%d pm=%d bme688=%d\n",
                sensors.shtc3Present(), sensors.scd41Present(),
                sensors.pmPresent(), sensors.bme688Present());
        return 1;
    }

    if (!o.json) {
        printf("\nRoom seed %u, %.1f h from %02u:%02u, one sample every %u s.\n",
               o.seed, o.hours, (startEpoch % 86400) / 3600, (startEpoch % 3600) / 60, o.intervalS);
        printf("Sensors column: T temp/rh  C co2  P particulates  G gas — a dot means no reading.\n\n");
        printHeader();
    }

    char json[640];
    int rows = 0;
    for (uint32_t epoch = startEpoch; epoch <= endEpoch; epoch += o.intervalS) {
        room.advanceTo(epoch);
        Readings r = sensors.sample(epoch);

        if (o.json) {
            if (readingsToJson(r, "inkplate5-env-monitor", json, sizeof(json))) printf("%s\n", json);
            else fprintf(stderr, "json buffer too small\n");
        } else {
            if (rows && rows % 24 == 0) printHeader();
            printRow(r);
        }
        fflush(stdout);
        ++rows;

        // The suite already moved the clock by the ~150 ms a sample costs.
        uint32_t remainingMs = o.intervalS * 1000 - 200;
        clk.advance(remainingMs);
        if (o.speed > 0.0f) {
            // Sleep the real time this interval represents.
            uint32_t us = (uint32_t)(o.intervalS / o.speed * 1000000.0f);
            struct timespec ts = { (long)(us / 1000000), (long)((us % 1000000) * 1000) };
            nanosleep(&ts, nullptr);
        }
    }
    return 0;
}
