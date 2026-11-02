SYNTHETIC QA INPUT, not operational data.
Wire endian is little. Controller simulator receives MEASUREMENT id=0x52. Body has Value:uint16. A mandatory shared header precedes the body, but its definition and role widths are not supplied. The total length cannot be established. Do not invent a header.
#include <stdint.h>
#include "SharedHeader.h" // referenced file not supplied
#define MEASUREMENT_ID 0x52
struct Measurement { struct SharedHeader Header; uint16_t Value; };
