"""Verify the committed demo asset without adding a runtime dependency."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _sub_blocks(data: bytes, offset: int) -> int:
    """Skip GIF data sub-blocks and return the first byte after the terminator."""
    while True:
        size = data[offset]
        offset += 1
        if size == 0:
            return offset
        offset += size


def _frames_and_duration(data: bytes) -> tuple[int, int]:
    if not data.startswith(b"GIF89a"):
        raise AssertionError("Demo must use the GIF89a animation format")
    packed = data[10]
    offset = 13 + (3 * (2 ** ((packed & 0b111) + 1)) if packed & 0b10000000 else 0)
    frames, duration, pending_delay = 0, 0, 0
    while offset < len(data):
        marker = data[offset]
        offset += 1
        if marker == 0x3B:
            break
        if marker == 0x21:
            label = data[offset]
            offset += 1
            if label == 0xF9:
                assert data[offset] == 4, "Invalid graphics control extension"
                pending_delay = int.from_bytes(data[offset + 2:offset + 4], "little") * 10
                offset += 6
            else:
                offset = _sub_blocks(data, offset)
        elif marker == 0x2C:
            descriptor = data[offset:offset + 9]
            assert len(descriptor) == 9, "Truncated image descriptor"
            offset += 9
            if descriptor[8] & 0b10000000:
                offset += 3 * (2 ** ((descriptor[8] & 0b111) + 1))
            offset += 1  # LZW minimum code size
            offset = _sub_blocks(data, offset)
            frames += 1
            duration += pending_delay
            pending_delay = 0
        else:
            raise AssertionError(f"Unexpected GIF block marker: {marker:#x}")
    return frames, duration


def main() -> None:
    asset = ROOT / "assets" / "freshguard-demo.gif"
    data = asset.read_bytes()
    frames, duration = _frames_and_duration(data)
    assert frames == 7, "Demo should retain a concise seven-scene story"
    assert 1_000 < duration < 30_000, "Demo should be watchable in under 30 seconds"
    assert len(data) > 10_000, "Demo asset appears unexpectedly small"
    print(f"PASS demo GIF: {frames} frames, {duration / 1000:.1f}s, GIF89a")


if __name__ == "__main__":
    main()
