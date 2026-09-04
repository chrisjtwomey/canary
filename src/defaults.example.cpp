// Copy to src/defaults.cpp and fill in. That file is gitignored so your
// credentials stay local. Definitions for the symbols EpdClient's
// defaults.h declares.
#include <stdint.h>

// The first page to fetch. After that the server names the next one.
char serverURL[] = "http://YOUR_SERVER_HOST:8080/breathe.png";
int serverRetries = 3;
// Seconds between fetches when the server does not say.
uint32_t serverDefaultRefreshSeconds = 300;

char wifiSSID[] = "XXXX";
char wifiPass[] = "XXXX";
int wifiRetries = 10;

char ntpHost[] = "pool.ntp.org";
char ntpTimezone[] = "Europe/Dublin";

bool mqttLoggerEnabled = false;
char mqttLoggerBroker[] = "localhost";
int mqttLoggerPort = 1883;
char mqttLoggerClientID[] = "inkplate5-env-monitor";
char mqttLoggerTopic[] = "mqtt/env-monitor-client";
int mqttLoggerRetries = 3;
