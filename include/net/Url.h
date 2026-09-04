#pragma once
#include <cstddef>
#include <cstring>

// Copies the scheme, host and port of url into out: "http://h:8080/x.png"
// gives "http://h:8080". Returns the length, or 0 when url has no host or
// out is too small; out is then empty.
inline size_t urlOrigin(const char* url, char* out, size_t len) {
    if (len) out[0] = '\0';
    const char* scheme = strstr(url, "://");
    if (!scheme) return 0;
    const char* host = scheme + 3;
    const char* path = strchr(host, '/');
    size_t n = path ? (size_t)(path - url) : strlen(url);
    if (n == (size_t)(host - url) || n + 1 > len) return 0;
    memcpy(out, url, n);
    out[n] = '\0';
    return n;
}
