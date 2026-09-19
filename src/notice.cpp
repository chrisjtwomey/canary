#include "head/Notice.h"

#include <Arduino.h>
#include <WiFi.h>

#include "epd.h"
#include "head/fonts/FrauncesDetail.h"
#include "log_utils.h"
#include "version.h"

// Each notice is a page the server's pipeline rendered, held in the firmware
// (board_build.embed_files) and drawn by the same call that draws a fetched
// page. The layout leaves its bottom free, and the two facts only known at
// run time go there in the pages' own face, at the size of their detail text.
// The symbols are the files' paths from the project root.
extern const uint8_t noticeUnreachable[] asm("_binary_include_head_notices_notice_unreachable_png_start");
extern const uint8_t noticeUnreachableEnd[] asm("_binary_include_head_notices_notice_unreachable_png_end");
extern const uint8_t noticeVersion[] asm("_binary_include_head_notices_notice_version_png_start");
extern const uint8_t noticeVersionEnd[] asm("_binary_include_head_notices_notice_version_png_end");

// Where the run-time lines go, on the Inkplate 5's 1280 x 720. The margin is
// the page's 6cqw; the lines sit in the 20cqh the notice leaves free.
static const int16_t kMargin = 77;
static const int16_t kFactY = 720 - 100;
static const int16_t kFooterY = 720 - 52;
static const uint16_t kInkSoft = 2;   // the pages' --ink-soft, in 3-bit greys

// What the panel holds when it is a notice; empty when it is a page.
static char shown[128] = "";

static void draw(const uint8_t* png, const uint8_t* end, const char* fact) {
    IBoard& board = epdBoard();
    board.clearDisplay();
    if (!board.drawPngFromBuffer((uint8_t*)png, (int32_t)(end - png), 0, 0, false, false))
        log(LOG_ERROR, "the notice image would not decode");

    board.setFont(&FrauncesDetail);
    board.setTextSize(1);
    board.setTextWrap(false);
    board.setTextColor(kInkSoft);
    board.setCursor(kMargin, kFactY);
    board.print(fact);

    // Enough to find the board on the network and know what it runs.
    char footer[96];
    snprintf(footer, sizeof(footer), "%s %s    %s", CLIENT_NAME, CLIENT_VERSION,
             WiFi.localIP().toString().c_str());
    board.setCursor(kMargin, kFooterY);
    board.print(footer);

    board.display();
}

static bool showOnce(const char* key, const uint8_t* png, const uint8_t* end, const char* fact) {
    if (strcmp(shown, key) == 0) return true;
    logf(LOG_NOTICE, "notice: %s", fact);
    draw(png, end, fact);
    strlcpy(shown, key, sizeof(shown));
    return true;
}

bool showVersionNotice(const char* ownVersion, const char* serverVersion) {
    char fact[112];
    snprintf(fact, sizeof(fact), "Server: %s    Display: %s", serverVersion, ownVersion);
    char key[128];
    snprintf(key, sizeof(key), "version %s %s", ownVersion, serverVersion);
    return showOnce(key, noticeVersion, noticeVersionEnd, fact);
}

bool showUnreachableNotice(const char* lastPage) {
    char fact[64];
    // RFC 3339: the date is the first ten characters, the hour and minute the
    // five after the "T". A clock that never set reads 1970.
    const bool known = lastPage && strlen(lastPage) >= 16 && strncmp(lastPage, "1970", 4) != 0;
    if (known) {
        snprintf(fact, sizeof(fact), "Last refresh: %.10s %.5s", lastPage, lastPage + 11);
    } else {
        snprintf(fact, sizeof(fact), "Last refresh: none since boot");
    }
    return showOnce("unreachable", noticeUnreachable, noticeUnreachableEnd, fact);
}

void noticeReplaced() {
    shown[0] = '\0';
}
