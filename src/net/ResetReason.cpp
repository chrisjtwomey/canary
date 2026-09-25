#include "net/ResetReason.h"

#ifndef NATIVE
#include <esp_system.h>
static_assert(ESP_RST_POWERON == 1 && ESP_RST_PANIC == 4 && ESP_RST_CPU_LOCKUP == 15,
              "esp_reset_reason_t is no longer in the order kNames follows");
#endif

// esp_reset_reason_t, in its order, from ESP_RST_UNKNOWN at 0.
static const char* const kNames[] = {
    "unknown", "power_on", "external", "software", "panic", "int_watchdog",
    "task_watchdog", "watchdog", "deep_sleep", "brownout", "sdio", "usb",
    "jtag", "efuse", "power_glitch", "cpu_lockup",
};

const char* resetReasonName(int reason) {
    const int n = sizeof(kNames) / sizeof(kNames[0]);
    return reason >= 0 && reason < n ? kNames[reason] : "unknown";
}
