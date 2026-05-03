// Generates a synthetic WAV buffer of silence. Just enough bytes to
// satisfy the upload endpoint and MinIO storage without checking in a
// real recording. The downstream transcription step is expected to
// fail on this fixture (no speech), which is fine — E2E tests only
// assert up to the upload-complete status.

const SAMPLE_RATE = 16_000;
const BITS_PER_SAMPLE = 16;
const NUM_CHANNELS = 1;

export function makeSilenceWav(durationSec: number): Buffer {
  if (durationSec <= 0) {
    throw new Error("durationSec must be > 0");
  }

  const bytesPerSample = BITS_PER_SAMPLE / 8;
  const sampleCount = Math.floor(SAMPLE_RATE * durationSec);
  const dataSize = sampleCount * NUM_CHANNELS * bytesPerSample;
  const byteRate = SAMPLE_RATE * NUM_CHANNELS * bytesPerSample;
  const blockAlign = NUM_CHANNELS * bytesPerSample;

  // 44-byte RIFF/WAV PCM header + PCM data.
  const header = Buffer.alloc(44);
  header.write("RIFF", 0, "ascii");
  header.writeUInt32LE(36 + dataSize, 4); // ChunkSize
  header.write("WAVE", 8, "ascii");
  header.write("fmt ", 12, "ascii");
  header.writeUInt32LE(16, 16); // Subchunk1Size (PCM)
  header.writeUInt16LE(1, 20); // AudioFormat = PCM
  header.writeUInt16LE(NUM_CHANNELS, 22);
  header.writeUInt32LE(SAMPLE_RATE, 24);
  header.writeUInt32LE(byteRate, 28);
  header.writeUInt16LE(blockAlign, 32);
  header.writeUInt16LE(BITS_PER_SAMPLE, 34);
  header.write("data", 36, "ascii");
  header.writeUInt32LE(dataSize, 40);

  // PCM samples are already zero-filled (silence).
  const pcm = Buffer.alloc(dataSize);

  return Buffer.concat([header, pcm]);
}
