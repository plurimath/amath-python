def caller_position(source, text, char_offset):
    if char_offset is None:
        return None, None
    return char_offset, len(source[:char_offset].encode("utf-8"))
