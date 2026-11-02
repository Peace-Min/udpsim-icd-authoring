SYNTHETIC QA INPUT, not operational data.
The controller receives RAW id=0x54. Wire endian is little. Code sends memcpy of struct Raw {uint8_t Id; uint8_t Size; uint8_t Flag; uint32_t Value;}. Id and Size have id/length roles. Compiler ABI, packing, padding and sizeof result are unavailable. No field-by-field serialization is supplied. Do not equate the C declaration order to a proven wire layout.
#include <stdint.h>
struct Raw { uint8_t Id; uint8_t Size; uint8_t Flag; uint32_t Value; };
// serializer.c: send_bytes((const unsigned char *)&frame, sizeof(frame));
