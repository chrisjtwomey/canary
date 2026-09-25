#include "head/Splash.h"

#include <Arduino.h>

#include "epd.h"
#include "head/Notice.h"
#include "head/ProgressBar.h"
#include "head/fonts/FrauncesDetailItalic.h"
#include "log_utils.h"

// The splash screen the server's pipeline rendered in black and white
// (scripts/notices.py), held in the firmware (board_build.embed_files).
extern const uint8_t splashPng[] asm("_binary_include_head_splash_png_start");
extern const uint8_t splashPngEnd[] asm("_binary_include_head_splash_png_end");

// The bar on the Inkplate 5's 1280 x 720, centred under the logo. The page
// sets the logo 60cqw wide in the middle of the panel (styles.css), so its
// lowest ink is at y 488.
static const int16_t kWidth = 1280;
static const int16_t kBarW = 512;
static const int16_t kBarH = 24;
static const int16_t kBarX = (kWidth - kBarW) / 2;
static const int16_t kBarY = 552;
static const int16_t kLine = 3;   // the outline
static const int16_t kGap = 4;    // between the outline and the fill
static const int16_t kFillX = kBarX + kLine + kGap;
static const int16_t kFillY = kBarY + kLine + kGap;
static const int16_t kFillW = kBarW - 2 * (kLine + kGap);
static const int16_t kFillH = kBarH - 2 * (kLine + kGap);
// The baseline of the line under the bar, in the pages' italic at the size of
// their detail text.
static const int16_t kLineY = 622;

// In black and white.
static const uint16_t kBlack = 1;
static const uint16_t kWhite = 0;

static ProgressBar bar;
static char offeredVersion[32] = "";

// Into the frame buffer, in black and white; the caller pushes it.
static void drawLogo() {
    IBoard& board = epdBoard();
    board.setBlackAndWhite(true);
    board.clearDisplay();
    if (!board.drawPngFromBuffer((uint8_t*)splashPng, (int32_t)(splashPngEnd - splashPng), 0, 0, false, false))
        log(LOG_ERROR, "the splash image would not decode");
    noticeReplaced();
}

static void writeLine() {
    char line[64];
    snprintf(line, sizeof(line), "Installing firmware %s...", offeredVersion);
    IBoard& board = epdBoard();
    board.setFont(&FrauncesDetailItalic);
    board.setTextSize(1);
    board.setTextWrap(false);
    board.setTextColor(kBlack);
    int16_t x, y;
    uint16_t w, h;
    board.getTextBounds(line, 0, kLineY, &x, &y, &w, &h);
    board.setCursor((kWidth - (int16_t)w) / 2 - x, kLineY);
    board.print(line);
}

static void fillBar(int steps) {
    const int16_t w = kFillW * steps / ProgressBar::kSteps;
    if (w > 0) epdBoard().fillRect(kFillX, kFillY, w, kFillH, kBlack);
}

void showSplash() {
    drawLogo();
    epdBoard().display();
    epdBoard().setBlackAndWhite(false);
}

void showUpdateProgress(int done, int total) {
    IBoard& board = epdBoard();
    switch (bar.update(done, total)) {
        case ProgressBar::FULL:
            drawLogo();
            board.fillRect(kBarX, kBarY, kBarW, kBarH, kBlack);
            board.fillRect(kBarX + kLine, kBarY + kLine, kBarW - 2 * kLine, kBarH - 2 * kLine, kWhite);
            fillBar(bar.filled);
            writeLine();
            board.display();
            break;
        case ProgressBar::PARTIAL:
            fillBar(bar.filled);
            board.partialDisplay();
            break;
        case ProgressBar::NONE:
            break;
    }
}

void beginUpdateProgress(const char* offered) {
    bar = ProgressBar{};
    strlcpy(offeredVersion, offered, sizeof(offeredVersion));
}

void endUpdateProgress() {
    epdBoard().setBlackAndWhite(false);
}
