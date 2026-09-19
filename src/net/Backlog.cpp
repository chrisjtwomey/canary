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
    lastLen_ = len;
    return true;
}

size_t RingBacklog::peekAt(uint32_t index, char* buf, size_t len) {
    if (index >= count_) return 0;
    size_t at = head_;
    for (uint32_t i = 0; i < index; ++i) at = (at + kHeaderBytes + lengthAt(at)) % size_;
    const size_t n = lengthAt(at);
    if (n >= len) return 0;
    read((at + kHeaderBytes) % size_, (uint8_t*)buf, n);
    buf[n] = '\0';
    return n;
}

void RingBacklog::pop() {
    if (count_ == 0) return;
    const size_t n = kHeaderBytes + lengthAt(head_);
    head_ = (head_ + n) % size_;
    used_ -= n;
    --count_;
}

size_t RingBacklog::lengthAt(size_t at) const {
    uint8_t header[kHeaderBytes];
    read(at, header, kHeaderBytes);
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

// Every chunk but the newest holds kPerChunk documents: kWorkBytes has room
// for that many of the longest, so a document never starts a chunk early.
size_t FileBacklog::peekAt(uint32_t index, char* buf, size_t len) {
    if (index >= count_) return 0;
    const uint32_t at = (uint32_t)headRec_ + index;
    const size_t n = readChunk((uint16_t)((head_ + at / kPerChunk) % kChunks));
    const uint16_t want = (uint16_t)(at % kPerChunk);
    size_t start = 0;
    for (uint16_t line = 0; line < want; ++line) {
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
    // 409 is the server saying this board's version cannot work with its own.
    // The document is sound and only the pairing is wrong, so it is held
    // until the two match again rather than dropped.
    if (httpStatus == 409) return TRY_LATER;
    if (httpStatus >= 400 && httpStatus < 500 && httpStatus != 408 && httpStatus != 429) {
        return REFUSED;
    }
    return TRY_LATER;
}

SendResult drainBacklog(IBacklog& backlog, IPoster& poster, uint32_t max, char* buf, size_t len) {
    SendResult r;
    for (uint32_t tried = 0; tried < max && backlog.count() > 0; ++tried) {
        if (backlog.peek(buf, len) == 0) {
            backlog.pop();
            ++r.dropped;
            continue;
        }
        r.status = poster.post(buf);
        const PostResult result = postResult(r.status);
        if (result == TRY_LATER) {
            r.wait = true;
            break;
        }
        backlog.pop();
        ++(result == POSTED ? r.posted : r.dropped);
    }
    return r;
}

uint32_t batchJson(IBacklog& backlog, uint32_t max, char* out, size_t len) {
    if (len < 3) return 0;
    size_t used = 1;
    uint32_t n = 0;
    while (n < max && n < backlog.count()) {
        // Room after the document for its terminator, and then for the ']'.
        char* at = out + used + (n ? 1 : 0);
        const size_t room = len - (size_t)(at - out);
        const size_t docLen = room > 1 ? backlog.peekAt(n, at, room - 1) : 0;
        if (docLen == 0) break;
        if (n) at[-1] = ',';
        used = (size_t)(at - out) + docLen;
        ++n;
    }
    if (n == 0) return 0;
    out[0] = '[';
    out[used] = ']';
    out[used + 1] = '\0';
    return n;
}

SendResult sendBatch(IBacklog& backlog, IPoster& poster, uint32_t max, char* batch, size_t len) {
    SendResult r;
    if (backlog.count() == 0) return r;
    const uint32_t n = batchJson(backlog, max, batch, len);
    if (n == 0) {
        backlog.pop();
        r.dropped = 1;
        return r;
    }
    r.status = poster.post(batch);
    switch (postResult(r.status)) {
        case POSTED:
            for (uint32_t i = 0; i < n; ++i) backlog.pop();
            r.posted = n;
            return r;
        case TRY_LATER:
            r.wait = true;
            return r;
        case REFUSED:
            break;
    }
    return drainBacklog(backlog, poster, n, batch, len);
}
