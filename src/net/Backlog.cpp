#include "net/Backlog.h"

#include <cstdio>
#include <cstring>

constexpr const char* FileBacklog::kIndexPath;

// ─── RingBacklog ─────────────────────────────────────────────────────────

bool RingBacklog::push(const char* doc, size_t len) {
    const size_t need = kHeaderBytes + len;
    if (len == 0 || len > 0xFFFF || need > size_) return false;
    while (size_ - used_ < need) pop();
    const uint8_t header[kHeaderBytes] = {(uint8_t)len, (uint8_t)(len >> 8)};
    const size_t tail = (head_ + used_) % size_;
    write(tail, header, kHeaderBytes);
    write((tail + kHeaderBytes) % size_, (const uint8_t*)doc, len);
    used_ += need;
    ++count_;
    return true;
}

size_t RingBacklog::peek(char* buf, size_t len) {
    if (count_ == 0) return 0;
    const size_t n = oldestLen();
    if (n >= len) return 0;
    read((head_ + kHeaderBytes) % size_, (uint8_t*)buf, n);
    buf[n] = '\0';
    return n;
}

void RingBacklog::pop() {
    if (count_ == 0) return;
    const size_t n = kHeaderBytes + oldestLen();
    head_ = (head_ + n) % size_;
    used_ -= n;
    --count_;
}

size_t RingBacklog::oldestLen() const {
    uint8_t header[kHeaderBytes];
    read(head_, header, kHeaderBytes);
    return (size_t)header[0] | (size_t)header[1] << 8;
}

void RingBacklog::read(size_t at, uint8_t* out, size_t len) const {
    const size_t first = len < size_ - at ? len : size_ - at;
    memcpy(out, mem_ + at, first);
    memcpy(out + first, mem_, len - first);
}

void RingBacklog::write(size_t at, const uint8_t* in, size_t len) {
    const size_t first = len < size_ - at ? len : size_ - at;
    memcpy(mem_ + at, in, first);
    memcpy(mem_, in + first, len - first);
}

// ─── FileBacklog ─────────────────────────────────────────────────────────

void FileBacklog::chunkPath(uint16_t chunk, char* path, size_t len) const {
    snprintf(path, len, "/backlog-%03u.jsonl", (unsigned)chunk);
}

size_t FileBacklog::readChunk(uint16_t chunk) {
    char path[32];
    chunkPath(chunk, path, sizeof(path));
    return files_.read(path, (uint8_t*)work_, workSize_);
}

bool FileBacklog::load() {
    char text[64];
    const size_t n = files_.read(kIndexPath, (uint8_t*)text, sizeof(text));
    if (n == 0 || n >= sizeof(text)) return false;
    text[n] = '\0';
    unsigned head, headRec, tail, tailRecs;
    unsigned long count;
    if (sscanf(text, "%u %u %u %u %lu", &head, &headRec, &tail, &tailRecs, &count) != 5) return false;
    if (head >= kChunks || tail >= kChunks || headRec > kPerChunk || tailRecs > kPerChunk ||
        count > (unsigned long)kChunks * kPerChunk) {
        return false;
    }
    head_ = (uint16_t)head;
    headRec_ = (uint16_t)headRec;
    tail_ = (uint16_t)tail;
    tailRecs_ = (uint16_t)tailRecs;
    count_ = (uint32_t)count;
    return true;
}

void FileBacklog::saveIndex() {
    char text[64];
    const int n = snprintf(text, sizeof(text), "%u %u %u %u %lu\n", (unsigned)head_,
                           (unsigned)headRec_, (unsigned)tail_, (unsigned)tailRecs_,
                           (unsigned long)count_);
    files_.write(kIndexPath, (const uint8_t*)text, (size_t)n);
}

// Move the tail to the next chunk. When that is the oldest one, every chunk
// is in use, and the documents still in the oldest are dropped.
void FileBacklog::startNextChunk() {
    tail_ = next(tail_);
    tailRecs_ = 0;
    if (tail_ != head_) return;
    count_ -= kPerChunk - headRec_;
    head_ = next(head_);
    headRec_ = 0;
}

bool FileBacklog::push(const char* doc, size_t len) {
    if (len == 0 || len >= kMaxDoc || memchr(doc, '\n', len)) return false;
    size_t used = 0;
    if (count_ > 0 && tailRecs_ < kPerChunk) {
        used = readChunk(tail_);
        if (used + len + 1 >= workSize_) {
            startNextChunk();
            used = 0;
        }
    } else if (count_ > 0) {
        startNextChunk();
    }
    memcpy(work_ + used, doc, len);
    work_[used + len] = '\n';
    char path[32];
    chunkPath(tail_, path, sizeof(path));
    if (!files_.write(path, (const uint8_t*)work_, used + len + 1)) return false;
    ++tailRecs_;
    ++count_;
    saveIndex();
    return true;
}

size_t FileBacklog::peek(char* buf, size_t len) {
    if (count_ == 0) return 0;
    const size_t n = readChunk(head_);
    size_t start = 0;
    for (uint16_t line = 0; line < headRec_; ++line) {
        const char* nl = (const char*)memchr(work_ + start, '\n', n - start);
        if (!nl) return 0;
        start = (size_t)(nl - work_) + 1;
    }
    const char* nl = (const char*)memchr(work_ + start, '\n', n - start);
    if (!nl) return 0;
    const size_t docLen = (size_t)(nl - work_) - start;
    if (docLen >= len) return 0;
    memcpy(buf, work_ + start, docLen);
    buf[docLen] = '\0';
    return docLen;
}

void FileBacklog::pop() {
    if (count_ == 0) return;
    --count_;
    ++headRec_;
    if (count_ == 0) {
        head_ = tail_;
        headRec_ = 0;
        tailRecs_ = 0;
    } else if (head_ != tail_ && headRec_ >= kPerChunk) {
        head_ = next(head_);
        headRec_ = 0;
    }
    saveIndex();
}

// ─── Posting ─────────────────────────────────────────────────────────────

// A 4xx is the server saying no to this document, which sending it again
// cannot change, except for a timeout (408) or a request to slow down (429).
PostResult postResult(int httpStatus) {
    if (httpStatus >= 200 && httpStatus < 300) return POSTED;
    if (httpStatus >= 400 && httpStatus < 500 && httpStatus != 408 && httpStatus != 429) {
        return REFUSED;
    }
    return TRY_LATER;
}

uint32_t drainBacklog(IBacklog& backlog, IPoster& poster, uint32_t max, char* buf, size_t len) {
    uint32_t gone = 0;
    while (gone < max && backlog.count() > 0) {
        if (backlog.peek(buf, len) > 0 && postResult(poster.post(buf)) == TRY_LATER) break;
        backlog.pop();
        ++gone;
    }
    return gone;
}
