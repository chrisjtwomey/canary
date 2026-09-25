#pragma once

// The client object's name for why the board last started: esp_reset_reason()'s
// value, "power_on" or "panic" for example, or "unknown" for a value
// ESP-IDF does not list.
const char* resetReasonName(int reason);
