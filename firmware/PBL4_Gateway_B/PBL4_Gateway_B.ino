/* PBL4 Gateway B R01 — ESP32-C3 + nRF24L01+ (UT-06 wiring).
 * RF: Protocol v2, 31 bytes LE, CRC16-CCITT-FALSE over bytes 0..28.
 * USB: NDJSON v2, 115200 8N1, LF, up to 4096 bytes before LF.
 * Build: ESP32C3 Dev Module, USB CDC On Boot Enabled, RF24 1.6.2.
 * cJSON is supplied by the ESP32 3.3.12 SDK.
 *
 * Share these RF address arrays with the other firmware owners, in order:
 *   common uplink  {0x50,0x34,0x01,0xC3,0xA5}
 *   table N        {0x50,0x34,0x01,0x01,N}, N=1..24
 *   staff 100+N    {0x50,0x34,0x01,0x02,N}, N=1..2
 * RF data field at offset 23: mV on telemetry uplink, table_id on
 * DISPATCH/ACCEPT_RECEIPT/DISPATCH_CANCEL, open_tasks on STAFF_STATUS,
 * reason code on ERROR. Offset 14 on a reply echoes its contact sequence.
 * PC is the sole source of application receipts and workflow state.
 */
#include <Arduino.h>
#include <SPI.h>
#include <RF24.h>
#include <cJSON.h>
#include <esp_random.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#ifndef PBL4_PC_BENCH
#define PBL4_PC_BENCH 0
#endif

class Gateway {
  static constexpr bool PcBench = PBL4_PC_BENCH != 0;
  static constexpr uint16_t Venue = 1;
  static constexpr size_t FrameSize = 31;
  static constexpr size_t UsbLimit = 4096;
  static constexpr size_t NodeCount = 26;
  static constexpr uint32_t WindowMs = 250;
  static constexpr uint32_t SettleMs = 3;
  static constexpr uint32_t TxGuardMs = 15;
  static constexpr uint32_t TestWindowMs = 60000;
  static constexpr uint32_t PartialMs = 2000;
  static constexpr uint32_t UsbDropMs = 30;
  static constexpr size_t QueueSize = 16;
  static constexpr size_t TagCount = 48;

  enum Kind : uint8_t {
    Call = 1, Poll = 2, Done = 3, Applied = 4, DeviceStatus = 5, Hello = 6,
    StaffPoll = 8, StaffApplied = 9, StaffAccept = 10,
    CallReceipt = 16, SetStatus = 17, DoneReceipt = 18,
    Dispatch = 24, AcceptReceipt = 25, Cancel = 26, StaffStatus = 27, Error = 255,
  };

  struct Frame {
    Kind kind{};
    uint16_t node{}, sequence{}, data{};
    uint32_t boot{}, reference{}, revision{}, tag{};
    uint8_t state{}, category{}, flags{};
  };
  struct Contact {
    Frame uplink{};
    uint32_t opened{};
    uint32_t generation{};
    bool active{}, test{};
  };
  struct TableLink {
    uint32_t boot{}, token{};
    char request[37]{};
  };
  struct TagLink {
    Frame command{};
    char uuid[37]{};
  };
  struct RadioReply {
    Frame frame{};
    uint32_t generation{};
  };
  struct UsbReply {
    char bytes[512]{};
    size_t size{}, sent{};
    uint32_t queued{};
    bool expires{};
  };

  RF24 radio{3, 10, 1000000};  // CE, CSN, SPI clock
  bool radioReady{}, usbPresent{};
  uint32_t lastUsbConnected{};
  uint32_t pcBenchLast{};
  uint8_t pcBenchReceipts{};
  Contact contacts[NodeCount]{};
  TableLink tableLinks[24]{};
  TagLink tags[TagCount]{};
  size_t nextTagSlot{};
  uint32_t gatewayBoot{}, nextTag{}, nextGeneration{};

  RadioReply down[QueueSize]{};
  size_t downHead{}, downCount{};
  UsbReply up[QueueSize]{};
  size_t upHead{}, upCount{};
  char input[UsbLimit + 1]{};
  size_t used{};
  uint32_t lastByte{};
  bool discard{};
  uint32_t rfIn{}, rfRejected{}, usbRejected{}, expired{}, txOK{}, txFail{}, drops{};

  static bool equal(const char *a, const char *b) { return a && b && strcmp(a, b) == 0; }
  static bool table(uint16_t id) { return id >= 1 && id <= 24; }
  static bool staff(uint16_t id) { return id >= 101 && id <= 102; }
  static size_t slot(uint16_t id) { return table(id) ? id - 1 : 24 + id - 101; }
  static const char *name(Kind kind) {
    switch (kind) {
      case Call: return "CALL";
      case Poll: return "STATUS_POLL";
      case Done: return "DONE";
      case Applied: return "STATUS_APPLIED";
      case DeviceStatus: return "DEVICE_STATUS";
      case Hello: return "NODE_HELLO";
      case StaffPoll: return "STAFF_POLL";
      case StaffApplied: return "STAFF_APPLIED";
      case StaffAccept: return "STAFF_ACCEPT";
      case CallReceipt: return "CALL_RECEIPT";
      case SetStatus: return "SET_REQUEST_STATUS";
      case DoneReceipt: return "DONE_RECEIPT";
      case Dispatch: return "DISPATCH";
      case AcceptReceipt: return "ACCEPT_RECEIPT";
      case Cancel: return "DISPATCH_CANCEL";
      case StaffStatus: return "STAFF_STATUS";
      case Error: return "ERROR";
      default: return "";
    }
  }
  static bool opensWindow(Kind kind) {
    return kind == Call || kind == Poll || kind == Done || kind == Hello ||
           kind == StaffPoll || kind == StaffAccept;
  }
  static uint16_t get16(const uint8_t *p) { return uint16_t(p[0]) | (uint16_t(p[1]) << 8); }
  static uint32_t get32(const uint8_t *p) {
    return uint32_t(get16(p)) | (uint32_t(get16(p + 2)) << 16);
  }
  static void put16(uint8_t *p, uint16_t value) { p[0] = value; p[1] = value >> 8; }
  static void put32(uint8_t *p, uint32_t value) {
    put16(p, value); put16(p + 2, value >> 16);
  }
  static uint16_t crc16(const uint8_t *bytes, size_t count) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < count; ++i) {
      crc ^= uint16_t(bytes[i]) << 8;
      for (int bit = 0; bit < 8; ++bit) {
        crc = uint16_t((crc << 1) ^ ((crc & 0x8000) ? 0x1021 : 0));
      }
    }
    return crc;
  }
  static void encode(const Frame &f, uint8_t *bytes) {
    bytes[0] = 2; bytes[1] = f.kind;
    put16(bytes + 2, Venue); put16(bytes + 4, f.node);
    put32(bytes + 6, f.boot); put32(bytes + 10, f.reference);
    put16(bytes + 14, f.sequence); put32(bytes + 16, f.revision);
    bytes[20] = f.state; bytes[21] = f.category; bytes[22] = f.flags;
    put16(bytes + 23, f.data); put32(bytes + 25, f.tag);
    put16(bytes + 29, crc16(bytes, 29));
  }
  static bool decodeUplink(const uint8_t *b, size_t length, Frame &f) {
    if (length != FrameSize || b[0] != 2 || get16(b + 2) != Venue ||
        get16(b + 29) != crc16(b, 29)) return false;
    f.kind = Kind(b[1]); f.node = get16(b + 4);
    f.boot = get32(b + 6); f.reference = get32(b + 10);
    f.sequence = get16(b + 14); f.revision = get32(b + 16);
    f.state = b[20]; f.category = b[21]; f.flags = b[22];
    f.data = get16(b + 23); f.tag = get32(b + 25);
    if (f.category > 2 || (f.flags & ~3) || ((f.flags & 1) && f.data > 10000)) return false;
    switch (f.kind) {
      case Call: return table(f.node) && f.reference && f.category;
      case Poll: case Done: return table(f.node) && f.reference;
      case Applied: return table(f.node) && f.reference && f.state <= 2;
      case DeviceStatus: case Hello: return table(f.node);
      case StaffPoll: return staff(f.node);
      case StaffApplied:
        return staff(f.node) && f.reference && f.revision && f.state >= 1 && f.state <= 3;
      case StaffAccept: return staff(f.node) && f.reference && f.revision;
      default: return false;
    }
  }
  static void eventId(const Frame &f, char *text, size_t size) {
    snprintf(text, size, "%u.%lu.%lu.%u.%s", unsigned(f.node),
             (unsigned long)f.boot, (unsigned long)f.reference, unsigned(f.sequence), name(f.kind));
  }

  bool enqueueUsb(const char *line, bool expires = false) {
    const size_t length = strlen(line);
    if (upCount == QueueSize || length >= sizeof(up[0].bytes) - 1) {
      ++drops;
      return false;
    }
    UsbReply &entry = up[(upHead + upCount) % QueueSize];
    memcpy(entry.bytes, line, length);
    entry.bytes[length] = '\n';
    entry.size = length + 1; entry.sent = 0;
    entry.queued = millis(); entry.expires = expires;
    ++upCount;
    return true;
  }
  void popUsb() { upHead = (upHead + 1) % QueueSize; --upCount; }
  void flushUsb() {
    for (unsigned i = 0; i < 4 && upCount; ++i) {
      UsbReply &entry = up[upHead];
      if (!entry.sent && entry.expires && millis() - entry.queued >= WindowMs - TxGuardMs) {
        ++expired;
        popUsb();
        continue;
      }
      if (!Serial) return;
      const int space = Serial.availableForWrite();
      if (space <= 0) return;
      size_t count = entry.size - entry.sent;
      if (count > size_t(space)) count = size_t(space);
      entry.sent += Serial.write(reinterpret_cast<const uint8_t *>(entry.bytes + entry.sent), count);
      if (entry.sent != entry.size) return;
      popUsb();
    }
  }

  bool verifyAppliedTag(const Frame &f) const {
    if (!f.tag || (f.kind != Applied && f.kind != StaffApplied)) return true;
    for (const TagLink &link : tags) {
      const Frame &c = link.command;
      if (c.tag != f.tag) continue;
      return c.node == f.node && c.boot == f.boot && c.reference == f.reference &&
             c.revision == f.revision && c.state == f.state;
    }
    // After a gateway reset or cache eviction the PC still checks identity/revision.
    return true;
  }
  uint32_t tagFor(const char *uuid, const Frame &frame) {
    if (!uuid) return 0;
    for (TagLink &link : tags) {
      if (equal(link.uuid, uuid) && link.command.node == frame.node && link.command.boot == frame.boot) {
        return link.command.tag;
      }
    }
    TagLink &link = tags[nextTagSlot];
    nextTagSlot = (nextTagSlot + 1) % TagCount;
    link.command = frame;
    if (++nextTag == 0) ++nextTag;
    link.command.tag = nextTag;
    strcpy(link.uuid, uuid);
    return nextTag;
  }

  bool forwardUplink(const uint8_t *bytes, size_t length, bool test = false) {
    Frame f;
    if (!decodeUplink(bytes, length, f) || !verifyAppliedTag(f)) { ++rfRejected; return false; }
    if (!test) ++rfIn;
    if (!Serial) { ++drops; return false; }
    const Contact &bench = contacts[0];
    if (!test && bench.test && withinWindow(bench, millis())) return false;
    Contact &contact = contacts[slot(f.node)];
    if (contact.active && contact.uplink.boot != f.boot) contact.active = false;

    // Durable correlation for retryable table events stays at the PC. Including a newly
    // learned UUID on CALL/DONE/HELLO retries would change the PC's fingerprint.
    const char *request = "null";
    char quoted[39];
    if (f.kind == Applied) {
      const TableLink &link = tableLinks[f.node - 1];
      if (link.request[0] && link.boot == f.boot && link.token == f.reference) {
        snprintf(quoted, sizeof(quoted), "\"%s\"", link.request);
        request = quoted;
      }
    }
    char id[72], payload[180] = "", line[512];
    eventId(f, id, sizeof(id));
    if (f.kind == Call) {
      snprintf(payload, sizeof(payload), "\"category\":\"%s\"", f.category == 1 ? "SERVICE" : "BILL");
    } else if (f.kind == Applied) {
      const char *led[] = {"OFF", "RED", "GREEN"};
      snprintf(payload, sizeof(payload), "\"led\":\"%s\",\"revision\":%lu", led[f.state], (unsigned long)f.revision);
    } else if (f.kind == StaffAccept || f.kind == StaffApplied) {
      snprintf(payload, sizeof(payload), "\"request_seq\":%lu,\"assignment_revision\":%lu",
               (unsigned long)f.reference, (unsigned long)f.revision);
      if (f.kind == StaffApplied) {
        const char *task[] = {"", "SHOWN", "ACCEPTED", "CLEARED"};
        size_t n = strlen(payload);
        snprintf(payload + n, sizeof(payload) - n, ",\"task\":\"%s\"", task[f.state]);
      }
    }
    if (f.flags || f.kind == DeviceStatus) {
      size_t n = strlen(payload);
      snprintf(payload + n, sizeof(payload) - n, "%s\"battery_low\":%s", n ? "," : "", f.flags & 2 ? "true" : "false");
      if (f.flags & 1) {
        n = strlen(payload);
        snprintf(payload + n, sizeof(payload) - n, ",\"battery_mv\":%u", unsigned(f.data));
      }
    }
    snprintf(line, sizeof(line), "{\"protocol_version\":2,\"venue_id\":%u,\"message_type\":\"%s\","
             "\"event_id\":\"%s\",\"node_id\":%u,\"boot_id\":%lu,\"call_token\":%lu,"
             "\"request_id\":%s,\"command_id\":null,\"payload\":{%s}}", unsigned(Venue),
             name(f.kind), id, unsigned(f.node), (unsigned long)f.boot,
             (unsigned long)(table(f.node) ? f.reference : 0), request, payload);
    if (!enqueueUsb(line, !test)) return false;
    if (opensWindow(f.kind)) contact = Contact{f, millis(), ++nextGeneration, true, test};
    return true;
  }

  static const cJSON *member(const cJSON *object, const char *key) {
    return cJSON_GetObjectItemCaseSensitive(object, key);
  }
  static const char *string(const cJSON *object, const char *key) {
    return cJSON_GetStringValue(member(object, key));
  }
  static bool number(const cJSON *object, const char *key, uint32_t &value, uint32_t limit = UINT32_MAX) {
    const cJSON *field = member(object, key);
    if (!cJSON_IsNumber(field) || !(field->valuedouble >= 0 && field->valuedouble <= limit)) return false;
    value = uint32_t(field->valuedouble);
    return field->valuedouble == value;
  }
  static bool uuid(const char *text) {
    if (!text || strlen(text) != 36) return false;
    for (size_t i = 0; i < 36; ++i) {
      const char c = text[i];
      if (i == 8 || i == 13 || i == 18 || i == 23) {
        if (c != '-') return false;
      } else if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'))) return false;
    }
    return true;
  }
  static bool optionalUuid(const cJSON *object, const char *key, const char *&value) {
    const cJSON *field = member(object, key);
    value = cJSON_GetStringValue(field);
    return !field || cJSON_IsNull(field) || uuid(value);
  }
  static uint16_t errorCode(const char *reason) {
    // 1..10, in this exact order. 255 is a valid unlisted PC reason.
    const char *reasons[] = {"wrong_venue", "unknown_node", "unknown_staff_device", "no_request_for_correlation",
                            "correlation_mismatch", "stale_device_status", "stale_assignment", "event_id_collision",
                            "unknown_command", "unknown_request"};
    for (uint16_t i = 0; i < sizeof(reasons) / sizeof(reasons[0]); ++i) if (equal(reason, reasons[i])) return i + 1;
    return 255;
  }
  static bool tableReply(const cJSON *root, const cJSON *payload, const Contact &window, Frame &f) {
    if (!table(f.node) || !number(root, "boot_id", f.boot) || !number(root, "call_token", f.reference) ||
        f.boot != window.uplink.boot || f.reference != window.uplink.reference ||
        !number(payload, "revision", f.revision)) return false;
    const char *led = string(payload, "led");
    if (equal(led, "OFF")) f.state = 0;
    else if (equal(led, "RED")) f.state = 1;
    else if (equal(led, "GREEN")) f.state = 2;
    else return false;
    const char *category = string(payload, "category");
    if (equal(category, "SERVICE")) f.category = 1;
    else if (equal(category, "BILL")) f.category = 2;
    else if (category || f.kind == CallReceipt) return false;
    return f.kind != DoneReceipt || f.state == 0;
  }
  static bool staffReply(const cJSON *payload, const Contact &window, Frame &f) {
    if (!staff(f.node)) return false;
    f.boot = window.uplink.boot;
    uint32_t data;
    if (f.kind == StaffStatus) {
      if (!number(payload, "open_tasks", data, UINT16_MAX)) return false;
    } else {
      if (!number(payload, "table_id", data, UINT16_MAX) || !data ||
          !number(payload, "request_seq", f.reference) || !f.reference ||
          !number(payload, "assignment_revision", f.revision) || !f.revision) return false;
      const char *category = string(payload, "category");
      const char *task = string(payload, "task");
      f.state = f.kind == Dispatch ? 1 : f.kind == AcceptReceipt ? 2 : 3;
      const char *tasks[] = {"", "SHOWN", "ACCEPTED", "CLEARED"};
      if (!equal(task, tasks[f.state])) return false;
      if (equal(category, "SERVICE")) f.category = 1;
      else if (equal(category, "BILL")) f.category = 2;
      else return false;
    }
    f.data = uint16_t(data);
    return true;
  }
  static bool errorReply(const cJSON *root, const cJSON *payload, const Contact &window, Frame &f) {
    char expected[72];
    eventId(window.uplink, expected, sizeof(expected));
    const char *reason = string(payload, "reason");
    if (!reason || !equal(string(root, "event_id"), expected)) return false;
    f.boot = window.uplink.boot;
    f.reference = window.uplink.reference;
    f.data = errorCode(reason);
    return true;
  }
  static bool withinWindow(const Contact &window, uint32_t now) {
    return window.active && now - window.opened < (window.test ? TestWindowMs : WindowMs - TxGuardMs);
  }
  void commandAck(const Frame &f, const char *command) {
    char json[300];
    snprintf(json, sizeof(json), "{\"protocol_version\":2,\"venue_id\":%u,\"message_type\":\"COMMAND_ACK\","
             "\"event_id\":\"gw.%lu.%s.ACK\",\"node_id\":%u,\"boot_id\":%lu,\"command_id\":\"%s\",\"payload\":{}}",
             unsigned(Venue), (unsigned long)gatewayBoot, command, unsigned(f.node), (unsigned long)gatewayBoot, command);
    enqueueUsb(json);
  }
  bool acceptDownlink(const cJSON *root) {
    uint32_t version, venue, node;
    const cJSON *payload = member(root, "payload");
    if (!cJSON_IsObject(root) || !cJSON_IsObject(payload) ||
        !number(root, "protocol_version", version) || version != 2 ||
        !number(root, "venue_id", venue) || venue != Venue ||
        !number(root, "node_id", node, UINT16_MAX) || (!table(node) && !staff(node))) return false;
    const char *type = string(root, "message_type");
    const char *command, *request;
    if (!optionalUuid(root, "command_id", command) || !optionalUuid(root, "request_id", request)) return false;
    Frame f;
    f.node = uint16_t(node);
    const Kind kinds[] = {CallReceipt, SetStatus, DoneReceipt, Dispatch, AcceptReceipt, Cancel, StaffStatus, Error};
    for (Kind k : kinds) if (equal(type, name(k))) { f.kind = k; break; }
    if (!f.kind) return false;
    const Contact &window = contacts[slot(f.node)];
    if (!withinWindow(window, millis())) { ++expired; return false; }
    if (!window.test || PcBench) {
      char expected[72];
      eventId(window.uplink, expected, sizeof(expected));
      if (!equal(string(root, "event_id"), expected)) { ++expired; return false; }
    }
    f.sequence = window.uplink.sequence;
    bool ok;
    if (f.kind <= DoneReceipt) ok = tableReply(root, payload, window, f);
    else if (f.kind == Error) ok = !command && errorReply(root, payload, window, f);
    else ok = staffReply(payload, window, f);
    if (!ok || downCount == QueueSize) return false;
    if (f.kind <= DoneReceipt && request && !window.test) {
      TableLink &link = tableLinks[f.node - 1];
      link.boot = f.boot; link.token = f.reference;
      strcpy(link.request, request);
    }
    f.tag = tagFor(command, f);
    down[(downHead + downCount) % QueueSize] = RadioReply{f, window.generation};
    ++downCount;
    if (command) commandAck(f, command);
    return true;
  }

  void sendOneRadioReply() {
    if (!downCount) return;
    const RadioReply reply = down[downHead];
    const Contact &window = contacts[slot(reply.frame.node)];
    const uint32_t now = millis();
    const bool live = window.generation == reply.generation && withinWindow(window, now);
    if (live && now - window.opened < SettleMs) return;
    downHead = (downHead + 1) % QueueSize;
    --downCount;
    if (!live) { ++expired; return; }
    uint8_t bytes[FrameSize];
    encode(reply.frame, bytes);
    if (window.test) {
      if (PcBench) {
        if (reply.frame.kind == CallReceipt && pcBenchReceipts < 2) ++pcBenchReceipts;
        return;
      }
      char text[9 + FrameSize * 2] = "TEST TX ";
      constexpr char hex[] = "0123456789ABCDEF";
      for (size_t i = 0; i < FrameSize; ++i) {
        text[8 + 2 * i] = hex[bytes[i] >> 4];
        text[9 + 2 * i] = hex[bytes[i] & 15];
      }
      enqueueUsb(text);
      return;
    }
    if (!radioReady) { ++txFail; return; }
    const uint16_t node = reply.frame.node;
    const uint8_t addr[] = {0x50, 0x34, uint8_t(Venue), uint8_t(table(node) ? 1 : 2),
                            uint8_t(table(node) ? node : node - 100)};
    radio.stopListening();
    radio.openWritingPipe(addr);
    const bool ack = radio.write(bytes, sizeof(bytes));
    radio.startListening();
    if (ack) ++txOK;
    else ++txFail;
  }

  void status() {
    char line[270];
    snprintf(line, sizeof(line), "STATUS FW=PBL4-GW-B-R01 RADIO=%s VENUE=%u CH=76 RF=31 USB=NDJSON2 WIN_MS=250 "
             "RF_IN=%lu RF_BAD=%lu USB_BAD=%lu WINDOW_DROP=%lu TX_ACK=%lu TX_FAIL=%lu QUEUE_DROP=%lu",
             radioReady && radio.isChipConnected() ? "OK" : "FAIL", unsigned(Venue),
             (unsigned long)rfIn, (unsigned long)rfRejected, (unsigned long)usbRejected, (unsigned long)expired,
             (unsigned long)txOK, (unsigned long)txFail, (unsigned long)drops);
    enqueueUsb(line);
  }
  void testCall() {
    for (Contact &contact : contacts) contact = Contact{};
    downCount = 0;
    const uint8_t vector[FrameSize] = {
      2, 1, 1, 0, 1, 0, 123, 0, 0, 0, 7, 0, 0, 0, 1, 0,
      0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0xEC, 0x53,
    };
    forwardUplink(vector, sizeof(vector), true);
  }

  void handleLine() {
    if (used && input[used - 1] == '\r') --used;
    if (!used) return;
    input[used] = '\0';
    if (!PcBench) {
      if (equal(input, "PING")) {
        enqueueUsb("PONG PBL4-GW-B-R01");
        return;
      }
      if (equal(input, "STATUS")) {
        status();
        return;
      }
      if (equal(input, "TEST CALL")) {
        testCall();
        return;
      }
      if (equal(input, "TEST STOP")) {
        contacts[0] = Contact{};
        downCount = 0;
        enqueueUsb("TEST STOPPED");
        return;
      }
    }
    cJSON *root = cJSON_ParseWithLengthOpts(input, used + 1, nullptr, true);
    if (!root || !acceptDownlink(root)) ++usbRejected;
    cJSON_Delete(root);
  }

  void readUsb() {
    if (used && !discard && millis() - lastByte >= PartialMs) {
      discard = true;
      ++usbRejected;
    }
    for (size_t i = 0; i < 512 && Serial.available(); ++i) {
      const int ch = Serial.read();
      if (ch < 0) return;
      if (ch == '\n') {
        if (!discard) handleLine();
        used = 0;
        discard = false;
      } else if (!discard) {
        if (used == UsbLimit || ch == 0) {
          discard = true;
          ++usbRejected;
        } else {
          input[used++] = char(ch);
          lastByte = millis();
        }
      }
    }
  }

  void readRadio() {
    for (size_t i = 0; i < 3 && radioReady && radio.available(); ++i) {
      const uint8_t length = radio.getDynamicPayloadSize();
      if (!length || length > 32) {
        ++rfRejected;
        radio.flush_rx();
        return;
      }
      uint8_t bytes[32];
      radio.read(bytes, length);
      forwardUplink(bytes, length);
    }
  }

  bool startRadio() {
    SPI.begin(4, 5, 6, 10);  // SCK, MISO, MOSI, CSN
    if (!radio.begin(&SPI)) return false;
    radio.setAddressWidth(5);
    radio.setChannel(76);
    if (!radio.setDataRate(RF24_1MBPS)) return false;
    radio.setPALevel(RF24_PA_LOW);
    radio.setCRCLength(RF24_CRC_16);
    radio.setAutoAck(true);
    radio.setRetries(3, 5);
    radio.enableDynamicPayloads();
    const uint8_t address[] = {0x50, 0x34, uint8_t(Venue), 0xC3, 0xA5};
    radio.openReadingPipe(1, address);
    radio.flush_rx();
    radio.flush_tx();
    radio.startListening();
    return radio.isChipConnected();
  }

 public:
  void begin() {
    gatewayBoot = esp_random();
    nextTag = gatewayBoot;
    Serial.setRxBufferSize(1024);
    Serial.setTxBufferSize(4096);
    Serial.setTxTimeoutMs(2);
    Serial.begin(115200);
    // Prime hardware CDC with an empty line, which the PC parser ignores.
    Serial.write(reinterpret_cast<const uint8_t *>("\n"), 1);
    radioReady = !PcBench && startRadio();
  }

  void tick() {
    const uint32_t now = millis();
    const bool connected = bool(Serial);
    if (connected) {
      usbPresent = true;
      lastUsbConnected = now;
    } else if (usbPresent && now - lastUsbConnected >= UsbDropMs) {
      usbPresent = false;
      used = 0;
      discard = false;
      upCount = downCount = 0;
      for (Contact &contact : contacts) contact = Contact{};
      Serial.write(reinterpret_cast<const uint8_t *>("\n"), 1);
    }
    if (PcBench && connected && pcBenchReceipts < 2 && now - pcBenchLast >= 3000) {
      testCall();
      pcBenchLast = now;
    }
    readRadio();
    readUsb();
    sendOneRadioReply();
    flushUsb();
  }
};

Gateway gateway;
void setup() { gateway.begin(); }
void loop() { gateway.tick(); }
