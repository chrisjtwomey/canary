#pragma once
#include <cstddef>
#include <cstdint>

// Readings documents waiting for the server to take them, oldest first. The
// code that posts does not know where they are kept.
class IBacklog {
public:
    virtual ~IBacklog() {}
    // Keep a document, dropping the oldest when there is no room. False when
    // this one cannot be kept at all.
    virtual bool push(const char* doc, size_t len) = 0;
    // Copy the document `index` places after the oldest into buf as a C
    // string and return its length. 0 when there is none, or when it does
    // not fit.
    virtual size_t peekAt(uint32_t index, char* buf, size_t len) = 0;
    size_t peek(char* buf, size_t len) { return peekAt(0, buf, len); }
    // Forget the oldest document.
    virtual void pop() = 0;
    virtual uint32_t count() const = 0;
    // About how many documents it holds when full, for the client status.
    virtual uint32_t capacity() const = 0;
    // Where the documents are kept, for the client status.
    virtual const char* where() const = 0;
};

// Documents in one block of memory, as a ring: PSRAM on the board, which a
// power cut empties, and the heap in the host tests.
class RingBacklog : public IBacklog {
public:
    RingBacklog(uint8_t* mem, size_t size, const char* where)
        : mem_(mem), size_(size), where_(where) {}

    bool push(const char* doc, size_t len) override;
    size_t peekAt(uint32_t index, char* buf, size_t len) override;
    void pop() override;
    uint32_t count() const override { return count_; }
    // At the size of the newest document; 0 before the first.
    uint32_t capacity() const override {
        return lastLen_ ? (uint32_t)(size_ / (kHeaderBytes + lastLen_)) : 0;
    }
    const char* where() const override { return where_; }

    // Each document is stored behind its length.
    static const size_t kHeaderBytes = 2;

private:
    size_t lengthAt(size_t at) const;
    void read(size_t at, uint8_t* out, size_t len) const;
    void write(size_t at, const uint8_t* in, size_t len);

    uint8_t*    mem_;
    size_t      size_;
    const char* where_;
    size_t      head_ = 0;
    size_t      used_ = 0;
    uint32_t    count_ = 0;
    size_t      lastLen_ = 0;
};

// Files read and written a whole file at a time, which is all the board
// offers for its SD card.
class IFileStore {
public:
    virtual ~IFileStore() {}
    // Replace the file with `len` bytes.
    virtual bool write(const char* path, const uint8_t* data, size_t len) = 0;
    // Up to maxLen bytes of the file, NUL-terminated when they fit. 0 when
    // it is missing or empty.
    virtual size_t read(const char* path, uint8_t* buf, size_t maxLen) = 0;
};

// Documents on a card, which keeps them across a restart. A file can only be
// read or written whole, so the documents go kPerChunk to a file, one per
// line, in a ring of kChunks files, and an index file says where the oldest
// and the newest are. When every file is full, the oldest file makes room.
class FileBacklog : public IBacklog {
public:
    // `work` holds one file while it is read or rewritten: kWorkBytes.
    FileBacklog(IFileStore& files, char* work, size_t workSize)
        : files_(files), work_(work), workSize_(workSize) {}

    // Take up the documents an earlier boot left, from the index. False when
    // there is no index to read, which leaves the backlog empty.
    bool load();

    bool push(const char* doc, size_t len) override;
    size_t peekAt(uint32_t index, char* buf, size_t len) override;
    void pop() override;
    uint32_t count() const override { return count_; }
    uint32_t capacity() const override { return (uint32_t)kChunks * kPerChunk; }
    const char* where() const override { return "sd"; }

    // The longest document kept, its newline included.
    static const size_t   kMaxDoc = 640;
    static const uint16_t kPerChunk = 100;
    // 20,000 readings: two weeks at one a minute.
    static const uint16_t kChunks = 200;
    static const size_t   kWorkBytes = kPerChunk * kMaxDoc + 1;
    static constexpr const char* kIndexPath = "/backlog.idx";

private:
    uint16_t next(uint16_t chunk) const { return (uint16_t)((chunk + 1) % kChunks); }
    void chunkPath(uint16_t chunk, char* path, size_t len) const;
    size_t readChunk(uint16_t chunk);
    void startNextChunk();
    void saveIndex();

    IFileStore& files_;
    char*       work_;
    size_t      workSize_;
    uint16_t    head_ = 0;       // the chunk holding the oldest document
    uint16_t    headRec_ = 0;    // its line in that chunk
    uint16_t    tail_ = 0;       // the chunk the next document goes in
    uint16_t    tailRecs_ = 0;   // documents already in it
    uint32_t    count_ = 0;
};

// What an HTTP status says about the document a POST carried: taken, never
// to be taken, or worth sending again. A status below 100 is the client's
// own error, no answer at all. 409, a version mismatch, is worth sending
// again: the document is sound and only the pairing is wrong.
enum PostResult : uint8_t { POSTED, REFUSED, TRY_LATER };
PostResult postResult(int httpStatus);

// Sends one request body and returns the HTTP status, or a negative client
// error.
class IPoster {
public:
    virtual ~IPoster() {}
    virtual int post(const char* body) = 0;
};

// What one pass of sending did.
struct SendResult {
    uint32_t posted = 0;    // documents the server took
    uint32_t dropped = 0;   // documents it refused, or too long to send
    bool     wait = false;  // the server must be tried again later
    int      status = 0;    // the last answer: an HTTP status, or a client error
};

// Post up to `max` documents one at a time, oldest first. A refused one is
// dropped, and so is one too long for `buf`; the first that must be tried
// later stays and ends the pass.
SendResult drainBacklog(IBacklog& backlog, IPoster& poster, uint32_t max, char* buf, size_t len);

// The oldest documents, up to `max`, as one JSON array in `out`. Returns how
// many went in: 0 when there are none, or the oldest does not fit.
uint32_t batchJson(IBacklog& backlog, uint32_t max, char* out, size_t len);

// Post up to `max` of the oldest documents as one array. A 2xx takes them all
// and a timeout, a 5xx or a 409 keeps them all. Any other 4xx sends each of
// them again alone, as drainBacklog does, so one document the server refuses
// costs only itself. An oldest document too long for `batch` is dropped.
SendResult sendBatch(IBacklog& backlog, IPoster& poster, uint32_t max, char* batch, size_t len);
