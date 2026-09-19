// The readings waiting for the server: held in memory or on a card, and
// sent oldest first, in batches.
#include <unity.h>

#include <cstdio>
#include <cstring>
#include <map>
#include <string>
#include <vector>

#include "net/Backlog.h"
#include "net/Stamp.h"

// ─── Fakes ───────────────────────────────────────────────────────────────

// A card: whole files by path, and a count of the writes each one took.
class FakeFiles : public IFileStore {
public:
    std::map<std::string, std::string> files;
    int writes = 0;
    bool failWrites = false;

    bool write(const char* path, const uint8_t* data, size_t len) override {
        ++writes;
        if (failWrites) return false;
        files[path] = std::string((const char*)data, len);
        return true;
    }

    size_t read(const char* path, uint8_t* buf, size_t maxLen) override {
        auto it = files.find(path);
        if (it == files.end() || it->second.empty()) return 0;
        size_t n = it->second.size() < maxLen ? it->second.size() : maxLen;
        memcpy(buf, it->second.data(), n);
        if (n < maxLen) buf[n] = '\0';
        return n;
    }
};

// A server: answers each post with the next status in `answers`, then 204.
class FakeServer : public IPoster {
public:
    std::vector<int> answers;
    std::vector<std::string> received;

    int post(const char* doc) override {
        received.push_back(doc);
        if (answers.empty()) return 204;
        int status = answers.front();
        answers.erase(answers.begin());
        return status;
    }
};

static std::string doc(int i) {
    char buf[64];
    snprintf(buf, sizeof(buf), "{\"ts\":%d,\"co2_ppm\":800}", i);
    return buf;
}

static bool push(IBacklog& b, int i) {
    std::string d = doc(i);
    return b.push(d.c_str(), d.size());
}

static std::string peek(IBacklog& b) {
    char buf[700];
    return b.peek(buf, sizeof(buf)) ? std::string(buf) : std::string();
}

static std::string peekAt(IBacklog& b, uint32_t i) {
    char buf[700];
    return b.peekAt(i, buf, sizeof(buf)) ? std::string(buf) : std::string();
}

// The documents from `first` to `last` as the array a batch carries.
static std::string batchOf(int first, int last) {
    std::string out = "[";
    for (int i = first; i <= last; ++i) out += (i > first ? "," : "") + doc(i);
    return out + "]";
}

void setUp() {}
void tearDown() {}

// ─── RingBacklog ─────────────────────────────────────────────────────────

void test_ring_hands_documents_back_oldest_first() {
    uint8_t mem[256];
    RingBacklog ring(mem, sizeof(mem), "psram");
    TEST_ASSERT_EQUAL_STRING("", peek(ring).c_str());
    for (int i = 1; i <= 3; ++i) TEST_ASSERT_TRUE(push(ring, i));
    TEST_ASSERT_EQUAL_UINT32(3, ring.count());
    for (int i = 1; i <= 3; ++i) {
        TEST_ASSERT_EQUAL_STRING(doc(i).c_str(), peek(ring).c_str());
        ring.pop();
    }
    TEST_ASSERT_EQUAL_UINT32(0, ring.count());
    ring.pop();   // nothing to forget
    TEST_ASSERT_EQUAL_UINT32(0, ring.count());
}

void test_ring_drops_the_oldest_when_full_and_wraps_round() {
    // The last documents are 23 bytes each, plus a 2-byte length: four fit
    // in 110 bytes, and five do not.
    uint8_t mem[110];
    RingBacklog ring(mem, sizeof(mem), "psram");
    for (int i = 1; i <= 50; ++i) TEST_ASSERT_TRUE(push(ring, i));
    TEST_ASSERT_EQUAL_UINT32(4, ring.count());
    for (int i = 47; i <= 50; ++i) {
        TEST_ASSERT_EQUAL_STRING(doc(i).c_str(), peek(ring).c_str());
        ring.pop();
    }
}

void test_ring_peeks_at_any_document_across_the_wrap() {
    uint8_t mem[110];
    RingBacklog ring(mem, sizeof(mem), "psram");
    for (int i = 1; i <= 6; ++i) push(ring, i);   // the oldest two are gone, the rest wrap
    TEST_ASSERT_EQUAL_UINT32(4, ring.count());
    for (uint32_t i = 0; i < 4; ++i) {
        TEST_ASSERT_EQUAL_STRING(doc(3 + (int)i).c_str(), peekAt(ring, i).c_str());
    }
    TEST_ASSERT_EQUAL_STRING("", peekAt(ring, 4).c_str());
    TEST_ASSERT_EQUAL_UINT32(4, ring.count());
}

void test_ring_refuses_a_document_bigger_than_itself() {
    uint8_t mem[16];
    RingBacklog ring(mem, sizeof(mem), "psram");
    TEST_ASSERT_FALSE(push(ring, 1));
    TEST_ASSERT_FALSE(ring.push("", 0));
    TEST_ASSERT_EQUAL_UINT32(0, ring.count());
    TEST_ASSERT_EQUAL_STRING("psram", ring.where());
}

void test_ring_peek_needs_room_for_the_terminator() {
    uint8_t mem[64];
    RingBacklog ring(mem, sizeof(mem), "psram");
    ring.push("abcd", 4);
    char small[4];
    TEST_ASSERT_EQUAL_UINT(0, ring.peek(small, sizeof(small)));
    char fits[5];
    TEST_ASSERT_EQUAL_UINT(4, ring.peek(fits, sizeof(fits)));
    TEST_ASSERT_EQUAL_STRING("abcd", fits);
}

// ─── FileBacklog ─────────────────────────────────────────────────────────

static char work[FileBacklog::kWorkBytes];

void test_ring_capacity_is_counted_in_documents_like_the_newest() {
    uint8_t mem[250];
    RingBacklog ring(mem, sizeof(mem), "psram");
    TEST_ASSERT_EQUAL_UINT32(0, ring.capacity());
    push(ring, 1);   // 22 bytes and its 2-byte length
    TEST_ASSERT_EQUAL_UINT32(10, ring.capacity());
    FakeFiles card;
    FileBacklog file(card, work, sizeof(work));
    TEST_ASSERT_EQUAL_UINT32((uint32_t)FileBacklog::kChunks * FileBacklog::kPerChunk, file.capacity());
}

void test_file_backlog_hands_documents_back_oldest_first_across_chunks() {
    FakeFiles card;
    FileBacklog backlog(card, work, sizeof(work));
    const int n = FileBacklog::kPerChunk * 2 + 5;
    for (int i = 1; i <= n; ++i) TEST_ASSERT_TRUE(push(backlog, i));
    TEST_ASSERT_EQUAL_UINT32(n, backlog.count());
    TEST_ASSERT_EQUAL_UINT(3 + 1, card.files.size());   // three chunks and the index
    for (int i = 1; i <= n; ++i) {
        TEST_ASSERT_EQUAL_STRING(doc(i).c_str(), peek(backlog).c_str());
        backlog.pop();
    }
    TEST_ASSERT_EQUAL_UINT32(0, backlog.count());
    TEST_ASSERT_EQUAL_STRING("", peek(backlog).c_str());
}

void test_file_backlog_peeks_at_any_document_across_chunks() {
    FakeFiles card;
    FileBacklog backlog(card, work, sizeof(work));
    for (int i = 1; i <= 250; ++i) push(backlog, i);
    for (int i = 1; i <= 30; ++i) backlog.pop();
    TEST_ASSERT_EQUAL_STRING(doc(31).c_str(), peekAt(backlog, 0).c_str());
    TEST_ASSERT_EQUAL_STRING(doc(100).c_str(), peekAt(backlog, 69).c_str());
    TEST_ASSERT_EQUAL_STRING(doc(101).c_str(), peekAt(backlog, 70).c_str());
    TEST_ASSERT_EQUAL_STRING(doc(250).c_str(), peekAt(backlog, 219).c_str());
    TEST_ASSERT_EQUAL_STRING("", peekAt(backlog, 220).c_str());
}

void test_file_backlog_survives_a_restart() {
    FakeFiles card;
    {
        FileBacklog before(card, work, sizeof(work));
        for (int i = 1; i <= 150; ++i) push(before, i);
        for (int i = 1; i <= 20; ++i) before.pop();
    }
    FileBacklog after(card, work, sizeof(work));
    TEST_ASSERT_TRUE(after.load());
    TEST_ASSERT_EQUAL_UINT32(130, after.count());
    TEST_ASSERT_EQUAL_STRING(doc(21).c_str(), peek(after).c_str());
    push(after, 151);
    for (int i = 21; i <= 151; ++i) {
        TEST_ASSERT_EQUAL_STRING(doc(i).c_str(), peek(after).c_str());
        after.pop();
    }
}

void test_file_backlog_without_an_index_starts_empty() {
    FakeFiles card;
    FileBacklog backlog(card, work, sizeof(work));
    TEST_ASSERT_FALSE(backlog.load());
    card.files[FileBacklog::kIndexPath] = "not an index";
    TEST_ASSERT_FALSE(backlog.load());
    card.files[FileBacklog::kIndexPath] = "999 0 0 0 5\n";
    TEST_ASSERT_FALSE_MESSAGE(backlog.load(), "a chunk past the ring is a corrupt index");
    TEST_ASSERT_EQUAL_UINT32(0, backlog.count());
}

void test_file_backlog_drops_the_oldest_chunk_when_every_chunk_is_full() {
    FakeFiles card;
    FileBacklog backlog(card, work, sizeof(work));
    const uint32_t capacity = (uint32_t)FileBacklog::kChunks * FileBacklog::kPerChunk;
    for (uint32_t i = 1; i <= capacity; ++i) push(backlog, (int)i);
    TEST_ASSERT_EQUAL_UINT32(capacity, backlog.count());
    TEST_ASSERT_EQUAL_STRING(doc(1).c_str(), peek(backlog).c_str());

    push(backlog, (int)capacity + 1);
    TEST_ASSERT_EQUAL_UINT32(capacity - FileBacklog::kPerChunk + 1, backlog.count());
    TEST_ASSERT_EQUAL_STRING(doc(FileBacklog::kPerChunk + 1).c_str(), peek(backlog).c_str());
}

void test_file_backlog_refuses_what_it_cannot_store_as_one_line() {
    FakeFiles card;
    FileBacklog backlog(card, work, sizeof(work));
    TEST_ASSERT_FALSE(backlog.push("{\n}", 3));
    std::string huge(FileBacklog::kMaxDoc, 'x');
    TEST_ASSERT_FALSE(backlog.push(huge.c_str(), huge.size()));
    card.failWrites = true;
    TEST_ASSERT_FALSE(push(backlog, 1));
    TEST_ASSERT_EQUAL_UINT32(0, backlog.count());
    TEST_ASSERT_EQUAL_STRING("sd", backlog.where());
}

// ─── Posting ─────────────────────────────────────────────────────────────

void test_post_result_reads_the_status() {
    TEST_ASSERT_EQUAL_INT(POSTED, postResult(204));
    TEST_ASSERT_EQUAL_INT(POSTED, postResult(200));
    TEST_ASSERT_EQUAL_INT(REFUSED, postResult(400));
    TEST_ASSERT_EQUAL_INT(REFUSED, postResult(413));
    TEST_ASSERT_EQUAL_INT(TRY_LATER, postResult(408));
    TEST_ASSERT_EQUAL_INT(TRY_LATER, postResult(429));
    TEST_ASSERT_EQUAL_INT(TRY_LATER, postResult(503));
    TEST_ASSERT_EQUAL_INT_MESSAGE(TRY_LATER, postResult(-1), "no connection");
}

void test_a_version_mismatch_is_held_not_dropped() {
    TEST_ASSERT_EQUAL_INT(TRY_LATER, postResult(409));
}

void test_drain_sends_the_oldest_few_per_pass() {
    uint8_t mem[1024];
    RingBacklog ring(mem, sizeof(mem), "psram");
    for (int i = 1; i <= 7; ++i) push(ring, i);
    FakeServer server;
    char buf[640];

    const SendResult r = drainBacklog(ring, server, 5, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_UINT32(5, r.posted);
    TEST_ASSERT_FALSE(r.wait);
    TEST_ASSERT_EQUAL_UINT(5, server.received.size());
    TEST_ASSERT_EQUAL_STRING(doc(1).c_str(), server.received[0].c_str());
    TEST_ASSERT_EQUAL_STRING(doc(5).c_str(), server.received[4].c_str());
    TEST_ASSERT_EQUAL_UINT32(2, ring.count());
}

void test_drain_stops_at_the_first_that_must_wait_and_keeps_it() {
    uint8_t mem[1024];
    RingBacklog ring(mem, sizeof(mem), "psram");
    for (int i = 1; i <= 4; ++i) push(ring, i);
    FakeServer server;
    server.answers = {204, -1};
    char buf[640];

    const SendResult r = drainBacklog(ring, server, 5, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_UINT32(1, r.posted);
    TEST_ASSERT_TRUE(r.wait);
    TEST_ASSERT_EQUAL_INT(-1, r.status);
    TEST_ASSERT_EQUAL_UINT32(3, ring.count());
    TEST_ASSERT_EQUAL_STRING(doc(2).c_str(), peek(ring).c_str());
}

void test_drain_drops_a_document_the_server_refuses() {
    uint8_t mem[1024];
    RingBacklog ring(mem, sizeof(mem), "psram");
    for (int i = 1; i <= 3; ++i) push(ring, i);
    FakeServer server;
    server.answers = {400};
    char buf[640];

    const SendResult r = drainBacklog(ring, server, 5, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_UINT32(2, r.posted);
    TEST_ASSERT_EQUAL_UINT32(1, r.dropped);
    TEST_ASSERT_EQUAL_UINT32(0, ring.count());
    TEST_ASSERT_EQUAL_UINT(3, server.received.size());
}

void test_drain_keeps_everything_while_the_versions_differ() {
    uint8_t mem[1024];
    RingBacklog ring(mem, sizeof(mem), "psram");
    for (int i = 1; i <= 3; ++i) push(ring, i);
    FakeServer server;
    server.answers = {409};
    char buf[640];

    const SendResult r = drainBacklog(ring, server, 5, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_UINT32(0, r.posted);
    TEST_ASSERT_TRUE(r.wait);
    TEST_ASSERT_EQUAL_UINT32(3, ring.count());
    TEST_ASSERT_EQUAL_STRING(doc(1).c_str(), peek(ring).c_str());
}

// ─── Batches ─────────────────────────────────────────────────────────────

void test_a_batch_is_the_oldest_documents_as_one_array() {
    uint8_t mem[1024];
    RingBacklog ring(mem, sizeof(mem), "psram");
    for (int i = 1; i <= 7; ++i) push(ring, i);
    char out[512];

    TEST_ASSERT_EQUAL_UINT32(5, batchJson(ring, 5, out, sizeof(out)));
    TEST_ASSERT_EQUAL_STRING(batchOf(1, 5).c_str(), out);
    TEST_ASSERT_EQUAL_UINT32_MESSAGE(7, ring.count(), "building a batch takes nothing out");
}

void test_a_batch_stops_at_the_document_that_does_not_fit() {
    uint8_t mem[1024];
    RingBacklog ring(mem, sizeof(mem), "psram");
    for (int i = 1; i <= 7; ++i) push(ring, i);
    const std::string two = batchOf(1, 2);
    std::vector<char> exact(two.size() + 1);

    TEST_ASSERT_EQUAL_UINT32(2, batchJson(ring, 5, exact.data(), exact.size()));
    TEST_ASSERT_EQUAL_STRING(two.c_str(), exact.data());
    std::vector<char> tooSmall(two.size());
    TEST_ASSERT_EQUAL_UINT32(1, batchJson(ring, 5, tooSmall.data(), tooSmall.size()));
    TEST_ASSERT_EQUAL_STRING(batchOf(1, 1).c_str(), tooSmall.data());
}

void test_an_empty_backlog_makes_no_batch() {
    uint8_t mem[64];
    RingBacklog ring(mem, sizeof(mem), "psram");
    char out[64];
    TEST_ASSERT_EQUAL_UINT32(0, batchJson(ring, 5, out, sizeof(out)));
    FakeServer server;
    const SendResult r = sendBatch(ring, server, 5, out, sizeof(out));
    TEST_ASSERT_EQUAL_UINT32(0, r.posted + r.dropped);
    TEST_ASSERT_TRUE(server.received.empty());
}

void test_a_taken_batch_leaves_in_one_request() {
    uint8_t mem[1024];
    RingBacklog ring(mem, sizeof(mem), "psram");
    for (int i = 1; i <= 7; ++i) push(ring, i);
    FakeServer server;
    server.answers = {200};
    char out[512];

    const SendResult r = sendBatch(ring, server, 5, out, sizeof(out));
    TEST_ASSERT_EQUAL_UINT32(5, r.posted);
    TEST_ASSERT_EQUAL_INT(200, r.status);
    TEST_ASSERT_EQUAL_UINT(1, server.received.size());
    TEST_ASSERT_EQUAL_STRING(batchOf(1, 5).c_str(), server.received[0].c_str());
    TEST_ASSERT_EQUAL_STRING(doc(6).c_str(), peek(ring).c_str());
}

void test_a_batch_the_server_cannot_take_now_stays_whole() {
    const int answers[] = {-1, 503, 409};
    for (int status : answers) {
        uint8_t mem[1024];
        RingBacklog ring(mem, sizeof(mem), "psram");
        for (int i = 1; i <= 3; ++i) push(ring, i);
        FakeServer server;
        server.answers = {status};
        char out[512];

        const SendResult r = sendBatch(ring, server, 5, out, sizeof(out));
        TEST_ASSERT_TRUE(r.wait);
        TEST_ASSERT_EQUAL_UINT32(0, r.posted + r.dropped);
        TEST_ASSERT_EQUAL_UINT(1, server.received.size());
        TEST_ASSERT_EQUAL_UINT32(3, ring.count());
    }
}

void test_a_refused_batch_goes_again_one_document_at_a_time() {
    uint8_t mem[1024];
    RingBacklog ring(mem, sizeof(mem), "psram");
    for (int i = 1; i <= 4; ++i) push(ring, i);
    FakeServer server;
    server.answers = {400, 204, 400, 204};   // the batch, then 1, 2 and 3 alone
    char out[512];

    const SendResult r = sendBatch(ring, server, 3, out, sizeof(out));
    TEST_ASSERT_EQUAL_UINT32(2, r.posted);
    TEST_ASSERT_EQUAL_UINT32(1, r.dropped);
    TEST_ASSERT_FALSE(r.wait);
    TEST_ASSERT_EQUAL_UINT(4, server.received.size());
    TEST_ASSERT_EQUAL_STRING(doc(2).c_str(), server.received[2].c_str());
    TEST_ASSERT_EQUAL_UINT32_MESSAGE(1, ring.count(), "only the batch is sent again");
    TEST_ASSERT_EQUAL_STRING(doc(4).c_str(), peek(ring).c_str());
}

void test_a_refused_batch_stops_alone_when_the_server_goes() {
    uint8_t mem[1024];
    RingBacklog ring(mem, sizeof(mem), "psram");
    for (int i = 1; i <= 3; ++i) push(ring, i);
    FakeServer server;
    server.answers = {413, 204, -1};
    char out[512];

    const SendResult r = sendBatch(ring, server, 3, out, sizeof(out));
    TEST_ASSERT_EQUAL_UINT32(1, r.posted);
    TEST_ASSERT_TRUE(r.wait);
    TEST_ASSERT_EQUAL_UINT32(2, ring.count());
    TEST_ASSERT_EQUAL_STRING(doc(2).c_str(), peek(ring).c_str());
}

void test_an_oldest_document_too_long_for_any_batch_is_dropped() {
    uint8_t mem[1024];
    RingBacklog ring(mem, sizeof(mem), "psram");
    const std::string longDoc(40, 'x');
    ring.push(longDoc.c_str(), longDoc.size());
    push(ring, 2);
    FakeServer server;
    char out[32];

    const SendResult r = sendBatch(ring, server, 5, out, sizeof(out));
    TEST_ASSERT_EQUAL_UINT32(1, r.dropped);
    TEST_ASSERT_TRUE(server.received.empty());
    TEST_ASSERT_EQUAL_STRING(doc(2).c_str(), peek(ring).c_str());
}

// ─── Readings taken before the clock ─────────────────────────────────────

static const char kUnstamped[] = "{\"ts\":0,\"device\":\"canary-dock\",\"co2_ppm\":800}";

void test_a_reading_before_the_clock_carries_its_uptime() {
    char out[128];
    TEST_ASSERT_TRUE(markUnstamped(kUnstamped, 42000, out, sizeof(out)) > 0);
    TEST_ASSERT_EQUAL_STRING(
        "{\"ts\":0,\"taken_ms\":42000,\"device\":\"canary-dock\",\"co2_ppm\":800}", out);
    uint32_t ms = 0;
    TEST_ASSERT_TRUE(unstampedAt(out, ms));
    TEST_ASSERT_EQUAL_UINT32(42000, ms);
    TEST_ASSERT_FALSE(unstampedAt(kUnstamped, ms));
    TEST_ASSERT_EQUAL_UINT_MESSAGE(0, markUnstamped(doc(5).c_str(), 1, out, sizeof(out)),
                                   "only a reading with no time is marked");
}

void test_the_clock_puts_the_time_in() {
    char marked[128], out[128];
    markUnstamped(kUnstamped, 42000, marked, sizeof(marked));
    ServerClock clock;
    TEST_ASSERT_EQUAL_UINT_MESSAGE(0, stamp(marked, clock, out, sizeof(out)), "no clock yet");
    clock.sync(1760000000, 102000);
    TEST_ASSERT_TRUE(stamp(marked, clock, out, sizeof(out)) > 0);
    TEST_ASSERT_EQUAL_STRING("{\"ts\":1759999940,\"device\":\"canary-dock\",\"co2_ppm\":800}", out);
}

void test_the_queue_is_stamped_in_order_and_the_rest_left_alone() {
    uint8_t mem[1024];
    RingBacklog ring(mem, sizeof(mem), "psram");
    char marked[128];
    for (uint32_t ms = 10000; ms <= 30000; ms += 10000) {
        markUnstamped(kUnstamped, ms, marked, sizeof(marked));
        ring.push(marked, strlen(marked));
    }
    push(ring, 7);
    ServerClock clock;
    clock.sync(1760000000, 40000);
    char buf[256], out[256];

    TEST_ASSERT_EQUAL_UINT32(3, stampQueue(ring, clock, buf, sizeof(buf), out, sizeof(out)));
    TEST_ASSERT_EQUAL_UINT32(4, ring.count());
    TEST_ASSERT_EQUAL_STRING("{\"ts\":1759999970,\"device\":\"canary-dock\",\"co2_ppm\":800}",
                             peekAt(ring, 0).c_str());
    TEST_ASSERT_EQUAL_STRING("{\"ts\":1759999990,\"device\":\"canary-dock\",\"co2_ppm\":800}",
                             peekAt(ring, 2).c_str());
    TEST_ASSERT_EQUAL_STRING(doc(7).c_str(), peekAt(ring, 3).c_str());
}

void test_a_full_queue_loses_nothing_to_stamping() {
    uint8_t mem[200];
    RingBacklog ring(mem, sizeof(mem), "psram");
    char marked[128];
    uint32_t pushed = 0;
    while (true) {
        markUnstamped(kUnstamped, 1000 * (pushed + 1), marked, sizeof(marked));
        const uint32_t before = ring.count();
        ring.push(marked, strlen(marked));
        if (ring.count() == before) break;   // full: the oldest made room
        ++pushed;
    }
    const uint32_t held = ring.count();
    ServerClock clock;
    clock.sync(1760000000, 1000000);
    char buf[256], out[256];

    TEST_ASSERT_EQUAL_UINT32(held, stampQueue(ring, clock, buf, sizeof(buf), out, sizeof(out)));
    TEST_ASSERT_EQUAL_UINT32(held, ring.count());
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_ring_hands_documents_back_oldest_first);
    RUN_TEST(test_ring_drops_the_oldest_when_full_and_wraps_round);
    RUN_TEST(test_ring_peeks_at_any_document_across_the_wrap);
    RUN_TEST(test_ring_capacity_is_counted_in_documents_like_the_newest);
    RUN_TEST(test_ring_refuses_a_document_bigger_than_itself);
    RUN_TEST(test_ring_peek_needs_room_for_the_terminator);
    RUN_TEST(test_file_backlog_hands_documents_back_oldest_first_across_chunks);
    RUN_TEST(test_file_backlog_peeks_at_any_document_across_chunks);
    RUN_TEST(test_file_backlog_survives_a_restart);
    RUN_TEST(test_file_backlog_without_an_index_starts_empty);
    RUN_TEST(test_file_backlog_drops_the_oldest_chunk_when_every_chunk_is_full);
    RUN_TEST(test_file_backlog_refuses_what_it_cannot_store_as_one_line);
    RUN_TEST(test_post_result_reads_the_status);
    RUN_TEST(test_a_version_mismatch_is_held_not_dropped);
    RUN_TEST(test_drain_keeps_everything_while_the_versions_differ);
    RUN_TEST(test_drain_sends_the_oldest_few_per_pass);
    RUN_TEST(test_drain_stops_at_the_first_that_must_wait_and_keeps_it);
    RUN_TEST(test_drain_drops_a_document_the_server_refuses);
    RUN_TEST(test_a_batch_is_the_oldest_documents_as_one_array);
    RUN_TEST(test_a_batch_stops_at_the_document_that_does_not_fit);
    RUN_TEST(test_an_empty_backlog_makes_no_batch);
    RUN_TEST(test_a_taken_batch_leaves_in_one_request);
    RUN_TEST(test_a_batch_the_server_cannot_take_now_stays_whole);
    RUN_TEST(test_a_refused_batch_goes_again_one_document_at_a_time);
    RUN_TEST(test_a_refused_batch_stops_alone_when_the_server_goes);
    RUN_TEST(test_an_oldest_document_too_long_for_any_batch_is_dropped);
    RUN_TEST(test_a_reading_before_the_clock_carries_its_uptime);
    RUN_TEST(test_the_clock_puts_the_time_in);
    RUN_TEST(test_the_queue_is_stamped_in_order_and_the_rest_left_alone);
    RUN_TEST(test_a_full_queue_loses_nothing_to_stamping);
    return UNITY_END();
}
