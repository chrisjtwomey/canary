// Copy to src/defaults.cpp and fill in. That file is gitignored so your
// credentials stay local.
//
// The server URL, the WiFi credentials and the MQTT block are also kept on
// the board, and a real value here is written there as it passes. That is
// what lets an image built by CI, carrying only placeholders, still connect.
#include "settings.h"

ClientConfig compiledDefaults() {
    ClientConfig cfg = {};

    cfg.serverURL = "http://YOUR_SERVER_HOST:8080/breathe.png";
    cfg.serverRetries = 3;
    cfg.defaultRefreshSeconds = 300;
    cfg.wifiSSID = "XXXX";
    cfg.wifiPass = "XXXX";
    cfg.wifiRetries = 10;
    cfg.ntpHost = "pool.ntp.org";
    cfg.ntpTimezone = "Europe/Dublin";
    cfg.mqttEnabled = false;
    cfg.mqttBroker = "XXXX";
    cfg.mqttPort = 1883;
    cfg.mqttClientID = "inkplate5-env-monitor";
    cfg.mqttTopic = "mqtt/env-monitor-client";
    cfg.mqttRetries = 3;

    return cfg;
}
