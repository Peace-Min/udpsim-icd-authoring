// Synthetic protocol, independent of operational ICDs.
// Simulator role: controller. Controller sends PING to the device.
// All wire integers are little endian. Fields are serialized in the order below.
// Common header: Id uint8 (message ID), Length uint8 (total bytes including header).
// PING: ID 17 (decimal), total length 3 bytes, body Value uint8.
// There is no sequence field and no implicit padding.
#include <stdint.h>
struct Header { uint8_t Id; uint8_t Length; };
struct Ping { struct Header header; uint8_t Value; };
