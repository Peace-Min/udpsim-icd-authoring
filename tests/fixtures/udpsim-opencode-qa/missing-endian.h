// Independent synthetic protocol, revision QA-UNKNOWN-20261030.
// Simulator role: controller. The physical meter transmits VOLTAGE_SAMPLE to the controller.
// Canonical ICD name: Synthetic missing-endian sample.
// Header in wire order: FrameId:uint16 role=id; FrameSize:uint16 role=length,
// where length includes the 4-byte header. There is no sequence field.
// Exactly one message: code VOLTAGE_SAMPLE, name "Synthetic voltage sample",
// ID 0x3B71, total wire length 6 bytes. Body: Voltage:uint16, no enums or arrays.
// The wire byte order is not documented. Do not infer it from this host C declaration.
// No padding or checksum exists. Resolve the absent wire byte order before completion.
#include <stdint.h>
struct VoltagePacket { uint16_t FrameId; uint16_t FrameSize; uint16_t Voltage; };
