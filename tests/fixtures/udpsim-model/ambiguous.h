// Synthetic protocol. Simulator role: controller; controller sends PING.
// Header: Id uint8 role=id, Length uint8 role=length (total packet bytes).
// PING ID=17, total length=4 bytes, body Reading uint16.
// The wire byte order is absent from this source and cannot be inferred.
#include <stdint.h>
struct Ping { uint8_t Id; uint8_t Length; uint16_t Reading; };
