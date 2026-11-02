SYNTHETIC QA INPUT, not operational data.
Little endian. Header Id:uint8(role=id), Size:uint8(role=length). Controller receives STREAM id=0x53. Body Count:uint8 followed by Data:uint8[Count]. Count changes in every packet; no fixed bound is a fixed wire count. A variable-length frame is mandatory, not an optional fixed-array alternative.
#include <stdint.h>
struct Stream { uint8_t Id; uint8_t Size; uint8_t Count; uint8_t Data[]; };
// serialize: write_u8(Id); write_u8(Size); write_u8(Count); write_bytes(Data, Count);
