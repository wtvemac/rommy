import ctypes
from enum import Enum

# By Eric MacDonald

# BORKED Johnson says: good day and have a cup of tea. Nothing else to say. Happy LZJs!
# https://youtu.be/r799U_-jAnk

# This algorithm is pretty aggressive with compressing but fast at decompressing
# I think it was built to save money on storage in the LC2.5 and BPS boxes.

class LZJ_VERSION(int, Enum):
    VERSIONX = 0x6C7A6A00 # None, echo back
    VERSION0 = 0x6C7A6A30 # lzj0: Testing
    VERSION1 = 0x6C7A6A31 # lzj1: UTV, BPS and LC2.5 bootroms, older BPS and LC2.5 approms
    VERSION2 = 0x6C7A6A32 # lzj2: BPS and LC2.5 approms
    VERSION3 = 0x6C7A6A33 # lzj3: CompressFS "LZJ64"
    
    def __str__(_self):
        return str(_self.name)
        
    @classmethod
    def has_name(_self, name):
        return hasattr(_self, name.upper())

    @classmethod
    def has_value(_self, value):
        return value in _self._value2member_map_

    @classmethod
    def get_value(_self, name):
        return getattr(_self, name)

class lzj():
    def __init__(self, version: LZJ_VERSION = LZJ_VERSION.VERSION0):
        self.clear(version)

    def clear(self, version: LZJ_VERSION = LZJ_VERSION.VERSION0):
        self.BLOCK_SIZE = 0x100
        self.MAX_LENGTH = self.BLOCK_SIZE + 0x08
        self.WEIGHT_PROFILE_SIZE = 0x200

        self.version = version

        self.uncompressed_data = bytearray()
        self.uncompressed_length = 0x00
        self.uncompressed_index = 0x00

        self.compressed_data = bytearray()
        self.compressed_length = 0x00
        self.compressed_index = 0x00
        self.compressed_flag_index = 0x00

        self.flag = 0x00
        self.flag_bit_index = 0

        self.next_block_position = -1

        self.match_block_index_length = 0
        self.match_block_position = 0
        self.match_offset_diff = 0

        self.CloseMatchesNOffsetDiffs = []
        self.DistantMatchesNLengths = []

        if self.version == LZJ_VERSION.VERSION0:
            # Used to find and extract matches
            self.OffsetChecks = [
                # Offset match <, offset encode <=, +ENC VAL, +NEG ENC VAL, & CLAMP, DETEC
                # Offset less than, +ENC VAL, +NEG ENC VAL, & CLAMP, DETEC
                [0x000002, 0x000001, 0x000000, 0x0000000, 0x00000f, 0x0000000], # Level 0   (no match)
                [0x000101, 0x000101, 0x000001, 0x00000ff, 0x0000ff, 0x0000100], # Level 1   (match offset < 0x101)
                [0x001101, 0x001101, 0x000101, 0x0000eff, 0x000fff, 0x0001000], # Level 2   (match offset < 0x1101)
                [0x011101, 0x011101, 0x011101, 0x01eeeff, 0x0fffff, 0x0300000], # Level 3   (match offset < 0x11101)
                [0x111101, 0x111101, 0x111001, 0x1eeefff, 0xffffff, 0x3000000]  # Level 4/5 (match offset < 0x111101)
            ]

            # Used to judge best match.
            # It may be better or worse than another match depending on the match offset difference and the match length.
            self.BitWeights = [
                # match 0 bytes, match 1, match 2, match 3, match 4, match 5, match 6, match 7, match 8, match 9+
                [0x09, 0x00, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff], # Level 0 (no match)
                [0xff, 0xff, 0x0c, 0x0d, 0x0d, 0x0f, 0x0f, 0x0f, 0x0f, 0x15], # Level 1 (match offset < 0x101)
                [0xff, 0xff, 0xff, 0x11, 0x11, 0x14, 0x14, 0x14, 0x14, 0x1a], # Level 2 (match offset < 0x1101)
                [0xff, 0xff, 0xff, 0xff, 0x15, 0x17, 0x17, 0x17, 0x17, 0x1d], # Level 3 (match offset < 0x11101)
                [0xff, 0xff, 0xff, 0xff, 0x19, 0x1b, 0x1b, 0x1b, 0x1b, 0x21], # Level 4 (match offset < 0x111101 from Find4ByteMatches)
                [0xff, 0xff, 0xff, 0xff, 0x19, 0x1b, 0x1b, 0x1b, 0x1b, 0x21], # Level 5 (match offset < 0x111101 from Find5PlusByteMatches)
            ]

            # Used to encode compressed output data
            self.EncoderConfig = [
                [
                    0x00, # Default encoder config.
                    False, # Can't copy previous offset
                    [
                        # match 2 bytes, match 3, match 4, match more
                        #   [encoded_offset_bits, encoded_match_offset adder, copy_prev_offset_bits (stop early) 0x00=always encode offset]
                        [[0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00]], # Level 0   (no match)
                        [[0x0b, -0x000001, 0x00], [0x0c,  0x0001ff, 0x00], [0x0a, -0x000001, 0x00], [0x0a, -0x000001, 0x00]], # Level 1   (match offset < 0x101)
                        [[0x00,  0x000000, 0x00], [0x10,  0x002eff, 0x00], [0x0e,  0x000eff, 0x00], [0x0f,  0x005eff, 0x00]], # Level 2   (match offset < 0x1101)
                        [[0x00,  0x000000, 0x00], [0x12,  0x05eeff, 0x00], [0x12,  0x05eeff, 0x00], [0x12,  0x00eeff, 0x00]], # Level 3   (match offset < 0x11101)
                        [[0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00], [0x16,  0x6eeeff, 0x00], [0x16,  0x1eeeff, 0x00]]  # Level 4/5 (match offset < 0x111101)
                    ]
                ]
            ]
        elif self.version == LZJ_VERSION.VERSION2:
            # Used to find and extract matches
            self.OffsetChecks = [
                # Offset match <, offset encode <=, +ENC VAL, +NEG ENC VAL, & CLAMP, DETEC
                [0x000002, 0x000001, 0x000000, 0x0000000, 0x00000f, 0x0000000], # Level 0   (no match)
                [0x000101, 0x000101, 0x000001, 0x00000ff, 0x0000ff, 0x0000100], # Level 1   (match offset < 0x101)
                [0x001001, 0x001001, 0x000101, 0x0000eff, 0x000fff, 0x0001000], # Level 2   (match offset < 0x1001)
                [0x011001, 0x011001, 0x011101, 0x01eeeff, 0x0fffff, 0x0300000], # Level 3   (match offset < 0x11001)
                [0x111001, 0x111001, 0x111001, 0x1eeefff, 0xffffff, 0x3000000]  # Level 4/5 (match offset < 0x111001)
            ]

            # Used to judge best match.
            # It may be better or worse than another match depending on the match offset difference and the match length.
            self.BitWeights = [
                # match 0 bytes, match 1, match 2, match 3, match 4, match 5, match 6, match 7, match 8, match 9+
                [0x09, 0x00, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff], # Level 0 (no match)
                [0xff, 0xff, 0x0c, 0x0d, 0x0d, 0x0f, 0x0f, 0x0f, 0x0f, 0x15], # Level 1 (match offset < 0x101)
                [0xff, 0xff, 0xff, 0x11, 0x11, 0x14, 0x14, 0x14, 0x14, 0x1a], # Level 2 (match offset < 0x1001)
                [0xff, 0xff, 0xff, 0xff, 0x15, 0x17, 0x17, 0x17, 0x17, 0x1d], # Level 3 (match offset < 0x11001)
                [0xff, 0xff, 0xff, 0xff, 0x19, 0x1b, 0x1b, 0x1b, 0x1b, 0x21], # Level 4 (match offset < 0x111101 from Find4ByteMatches)
                [0xff, 0xff, 0xff, 0xff, 0x19, 0x1b, 0x1b, 0x1b, 0x1b, 0x21], # Level 5 (match offset < 0x111101 from Find5PlusByteMatches)
                [0xff, 0xff, 0xff, 0x09, 0x09, 0x0b, 0x0b, 0x0b, 0x0b, 0x09], # Copy offset weights 1 (offset <= 0x111101)
                [0xff, 0xff, 0xff, 0x09, 0x09, 0x0c, 0x0c, 0x0c, 0x0c, 0x09]  # Copy offset weights 2 (offset > 0x111101)
            ]

            # Used to encode compressed output data
            self.EncoderConfig = [
                [
                    0x00, # Default encoder config.
                    True, # Can copy previous offset
                    [
                        # match 2 bytes, match 3, match 4, match more
                        #   [encoded_offset_bits, encoded_match_offset adder, copy_prev_offset_0_bits (stop early) 0x00=always encode offset
                        [[0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00]], # Level 0   (no match)
                        [[0x0b, -0x000001, 0x00], [0x0c,  0x0001ff, 0x04], [0x0a, -0x000001, 0x04], [0x0a, -0x000001, 0x04]], # Level 1   (match offset < 0x101)
                        [[0x00,  0x000000, 0x00], [0x10,  0x002fff, 0x04], [0x0e,  0x000fff, 0x04], [0x0e,  0x002fff, 0x04]], # Level 2   (match offset < 0x1001)
                        [[0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00], [0x12,  0x01efff, 0x04], [0x12,  0x00efff, 0x04]], # Level 3   (match offset < 0x11001)
                        [[0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00], [0x16,  0x2eefff, 0x04], [0x16,  0x1eefff, 0x04]]  # Level 4/5 (match offset < 0x111001)
                    ]
                ],
                [
                    0x111001, # Used to encode compressed output data, after 0x111001
                    True, # Can copy previous offset
                    [
                        # match 2 bytes, match 3, match 4, match more
                        #   [encoded_offset_bits, encoded_match_offset adder, copy_prev_offset_bits (stop early) 0x00=always encode offset]
                        [[0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00]], # Level 0   (no match)
                        [[0x0b, -0x000001, 0x00], [0x0c,  0x0001ff, 0x04], [0x0a, -0x000001, 0x04], [0x0a, -0x000001, 0x05]], # Level 1   (match offset < 0x101)
                        [[0x00,  0x000000, 0x00], [0x10,  0x002fff, 0x04], [0x0e,  0x000fff, 0x04], [0x0f,  0x005fff, 0x05]], # Level 2   (match offset < 0x1001)
                        [[0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00], [0x12,  0x01efff, 0x04], [0x12,  0x00efff, 0x05]], # Level 3   (match offset < 0x11001)
                        [[0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00], [0x16,  0x2eefff, 0x04], [0x16,  0x1eefff, 0x05]]  # Level 4/5 (match offset < 0x111001)
                    ],
                    
                ]
            ]
        elif self.version == LZJ_VERSION.VERSION3:
            # Used to find and extract matches
            self.OffsetChecks = [
                # Offset match <, offset encode <=, +ENC VAL, +NEG ENC VAL, & CLAMP, DETEC
                [0x000002, 0x000001, 0x000000, 0x0000000, 0x00000f, 0x0000000], # Level 0   (no match)
                [0x000101, 0x000101, 0x000001, 0x00000ff, 0x0000ff, 0x0000100], # Level 1   (match offset < 0x101)
                [0x001101, 0x001101, 0x000101, 0x0000eff, 0x000fff, 0x0001000], # Level 2   (match offset < 0x1101)
                [0x011101, 0x011101, 0x011101, 0x01eeeff, 0x0fffff, 0x0300000], # Level 3   (match offset < 0x11101)
                [0x111101, 0x111101, 0x111001, 0x1eeefff, 0xffffff, 0x3000000]  # Level 4/5 (match offset < 0x111101)
            ]

            # Used to judge best match.
            # It may be better or worse than another match depending on the match offset difference and the match length.
            self.BitWeights = [
                # match 0 bytes, match 1, match 2, match 3, match 4, match 5, match 6, match 7, match 8, match 9+
                [0x09, 0x00, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff], # Level 0 (no match)
                [0xff, 0xff, 0x0c, 0x0d, 0x0d, 0x0f, 0x0f, 0x0f, 0x0f, 0x15], # Level 1 (match offset < 0x101)
                [0xff, 0xff, 0xff, 0x11, 0x10, 0x12, 0x12, 0x12, 0x12, 0x18], # Level 2 (match offset < 0x1101)
                [0xff, 0xff, 0xff, 0xff, 0x15, 0x17, 0x17, 0x17, 0x17, 0x1d], # Level 3 (match offset < 0x11101)
                [0xff, 0xff, 0xff, 0xff, 0x19, 0x1b, 0x1b, 0x1b, 0x1b, 0x21], # Level 4 (match offset < 0x111101 from Find4ByteMatches)
                [0xff, 0xff, 0xff, 0xff, 0x19, 0x1b, 0x1b, 0x1b, 0x1b, 0x21], # Level 5 (match offset < 0x111101 from Find5PlusByteMatches)
            ]

            # Used to encode compressed output data
            self.EncoderConfig = [
                [
                    0x00, # Default encoder config.
                    False, # Can't copy previous offset
                    [
                        # match 2 bytes, match 3, match 4, match more
                        #   [encoded_offset_bits, encoded_match_offset adder, copy_prev_offset_bits (stop early) 0x00=always encode offset]
                        [[0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00]], # Level 0   (no match)
                        [[0x0b, -0x000001, 0x00], [0x0c,  0x0001ff, 0x00], [0x0a, -0x000001, 0x00], [0x0a, -0x000001, 0x00]], # Level 1   (match offset < 0x101)
                        [[0x00,  0x000000, 0x00], [0x10,  0x002eff, 0x00], [0x0d,  0x000eff, 0x00], [0x0d,  0x000eff, 0x00]], # Level 2   (match offset < 0x1101)
                        [[0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00], [0x12,  0x00eeff, 0x00], [0x12,  0x00eeff, 0x00]], # Level 3   (match offset < 0x11101)
                        [[0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00], [0x16,  0x00eeff, 0x00], [0x16,  0x00eeff, 0x00]]  # Level 4/5 (match offset < 0x111101)
                    ]
                ]
            ]
        else: # All others (pretty much VERSION1)
            # Used to find and extract matches
            self.OffsetChecks = [
                # Offset match <, offset encode <=, +ENC VAL, +NEG ENC VAL, & CLAMP, DETEC
                [0x000002, 0x000001, 0x000000, 0x0000000, 0x00000f, 0x0000000], # Level 0   (no match)
                [0x000101, 0x000101, 0x000001, 0x00000ff, 0x0000ff, 0x0000100], # Level 1   (match offset < 0x101)
                [0x001101, 0x001101, 0x000101, 0x0000eff, 0x000fff, 0x0001000], # Level 2   (match offset < 0x1101)
                [0x011101, 0x011101, 0x011101, 0x01eeeff, 0x0fffff, 0x0300000], # Level 3   (match offset < 0x11101)
                [0x111101, 0x111101, 0x111001, 0x1eeefff, 0xffffff, 0x3000000]  # Level 4/5 (match offset < 0x111101)
            ]

            # Used to judge best match.
            # It may be better or worse than another match depending on the match offset difference and the match length.
            self.BitWeights = [
                # match 0 bytes, match 1, match 2, match 3, match 4, match 5, match 6, match 7, match 8, match 9+
                [0x09, 0x00, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff], # Level 0 (no match)
                [0xff, 0xff, 0x0c, 0x0d, 0x0d, 0x0f, 0x0f, 0x0f, 0x0f, 0x15], # Level 1 (match offset < 0x101)
                [0xff, 0xff, 0xff, 0x11, 0x11, 0x14, 0x14, 0x14, 0x14, 0x1a], # Level 2 (match offset < 0x1101)
                [0xff, 0xff, 0xff, 0xff, 0x15, 0x17, 0x17, 0x17, 0x17, 0x1d], # Level 3 (match offset < 0x11101)
                [0xff, 0xff, 0xff, 0xff, 0x19, 0x1b, 0x1b, 0x1b, 0x1b, 0x21], # Level 4 (match offset < 0x111101 from Find4ByteMatches)
                [0xff, 0xff, 0xff, 0xff, 0x19, 0x1b, 0x1b, 0x1b, 0x1b, 0x21], # Level 5 (match offset < 0x111101 from Find5PlusByteMatches)
            ]

            # Used to encode compressed output data
            self.EncoderConfig = [
                [
                    0x00, # Default encoder config.
                    False, # Can't copy previous offset
                    [
                        # match 2 bytes, match 3, match 4, match more
                        #   [encoded_offset_bits, encoded_match_offset adder, copy_prev_offset_bits (stop early) 0x00=always encode offset]
                        [[0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00]], # Level 0   (no match)
                        [[0x0b, -0x000001, 0x00], [0x0c,  0x0001ff, 0x00], [0x0a, -0x000001, 0x00], [0x0a, -0x000001, 0x00]], # Level 1   (match offset < 0x101)
                        [[0x00,  0x000000, 0x00], [0x10,  0x002eff, 0x00], [0x0e,  0x000eff, 0x00], [0x0f,  0x005eff, 0x00]], # Level 2   (match offset < 0x1101)
                        [[0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00], [0x12,  0x05eeff, 0x00], [0x12,  0x00eeff, 0x00]], # Level 3   (match offset < 0x11101)
                        [[0x00,  0x000000, 0x00], [0x00,  0x000000, 0x00], [0x16,  0x6eeeff, 0x00], [0x16,  0x1eeeff, 0x00]]  # Level 4/5 (match offset < 0x111101)
                    ]
                ]
            ]

    def Find5PlusByteMatches(self, findMatchLength, byteNM1MatchesIndexStart, byteNM1MatchesIndexEnd, byteNM2MatchesIndexStart, flipped, WordMatches, ByteMatches, byteNMatches):
        FlipperMatches1 = ByteMatches
        FlipperMatches2 = WordMatches
        if flipped:
            FlipperMatches1 = WordMatches
            FlipperMatches2 = ByteMatches
        else:
            FlipperMatches1 = ByteMatches
            FlipperMatches2 = WordMatches

        currentFindLength = findMatchLength

        while byteNM1MatchesIndexStart != byteNM1MatchesIndexEnd and currentFindLength < self.MAX_LENGTH:
            byteNM1MatchesLength = (byteNM1MatchesIndexEnd - byteNM1MatchesIndexStart) & 0xffffffff

            if byteNM1MatchesLength < 0x64:
                highestByte = -1
                lowestByte = 0x100
                noMatchCount = 0

                if byteNM1MatchesIndexEnd >= byteNM1MatchesIndexStart:
                    matchesIndex = byteNM1MatchesIndexStart
                    while byteNM1MatchesIndexEnd >= matchesIndex:
                        byte = self.uncompressed_data[(FlipperMatches2[matchesIndex] + (currentFindLength - 1))]

                        if byteNMatches[byte] == 0:
                            noMatchCount += 1

                        if byte < lowestByte:
                            lowestByte = byte

                        if byte > highestByte:
                            highestByte = byte

                        byteNMatches[byte] += 1
                        matchesIndex += 1

                    if noMatchCount == 1:
                        currentFindLength += 1
                        byteNMatches[highestByte] = 0
                        continue
                    elif noMatchCount == 2:
                        byteNMatches[highestByte] += byteNMatches[lowestByte]
                    else:
                        cVar9 = 0
                        byte = lowestByte
                        while byte <= highestByte:
                            cVar9 += byteNMatches[byte]
                            byteNMatches[byte] = cVar9
                            byte += 1

                matchesIndex = byteNM1MatchesIndexEnd
                while byteNM1MatchesIndexStart <= matchesIndex:
                    uncompressed_index = FlipperMatches2[matchesIndex]
                    byte = self.uncompressed_data[(uncompressed_index + (currentFindLength - 1))]

                    byteNMatches[byte] -= 1
                    FlipperMatches1[byteNM2MatchesIndexStart + byteNMatches[byte]] = uncompressed_index

                    matchesIndex -= 1

                if noMatchCount == 2:
                    byteNMatches[highestByte] = 0
                elif lowestByte <= highestByte:
                    for byte in range(lowestByte, highestByte + 1):
                        byteNMatches[byte] = 0
            else:
                matchesIndex = byteNM1MatchesIndexStart
                while matchesIndex <= byteNM1MatchesIndexEnd:
                    byte = self.uncompressed_data[(FlipperMatches2[matchesIndex] + (currentFindLength - 1))]

                    byteNMatches[byte] += 1
                    matchesIndex += 1

                totalCount = 0
                for byte in range(0x100):
                    totalCount += byteNMatches[byte]
                    byteNMatches[byte] = totalCount

                matchesIndex = byteNM1MatchesIndexEnd
                while byteNM1MatchesIndexStart <= matchesIndex:
                    uncompressed_index = FlipperMatches2[matchesIndex]
                    byte = self.uncompressed_data[uncompressed_index + (currentFindLength - 1)]

                    byteNMatches[byte] -= 1
                    FlipperMatches1[byteNM2MatchesIndexStart + byteNMatches[byte]] = uncompressed_index

                    matchesIndex -= 1

                for i in range(len(byteNMatches)):
                    byteNMatches[i] = 0x00000000

            byteNMatchesIndexStart = byteNM2MatchesIndexStart + 0
            byteNMatchesIndexEnd = byteNM2MatchesIndexStart + byteNM1MatchesLength
            prevUncompressedIndex = FlipperMatches1[byteNM2MatchesIndexStart + 0]
            prevByte = self.uncompressed_data[(FlipperMatches1[byteNM2MatchesIndexStart + 0] + (currentFindLength - 1))]
            for checkMatchIndex in range((byteNM2MatchesIndexStart + 1) & 0xffffffff, byteNMatchesIndexEnd + 1):
                curUncompressedIndex = FlipperMatches1[checkMatchIndex]
                curByte = self.uncompressed_data[(curUncompressedIndex + (currentFindLength - 1))]

                if prevByte == curByte:
                    matchDiff = (curUncompressedIndex - prevUncompressedIndex) & 0xffffffff

                    if matchDiff < self.OffsetChecks[1][0]:
                        self.CloseMatchesNOffsetDiffs[curUncompressedIndex] = matchDiff + self.OffsetChecks[1][3]
                    elif matchDiff < self.OffsetChecks[2][0]:
                        self.DistantMatchesNLengths[curUncompressedIndex] = matchDiff + self.OffsetChecks[2][3]
                    elif matchDiff < self.OffsetChecks[3][0]: 
                        self.DistantMatchesNLengths[curUncompressedIndex] = (self.DistantMatchesNLengths[curUncompressedIndex] & 0x7fff) | ((matchDiff + self.OffsetChecks[3][3]) << 0x0f)
                    elif matchDiff < self.OffsetChecks[4][0]:
                        self.DistantMatchesNLengths[curUncompressedIndex] = (self.DistantMatchesNLengths[curUncompressedIndex] & 0xffffffffffffffff) | ((matchDiff + self.OffsetChecks[4][3]) << 0x47)
                else:
                    if byteNMatchesIndexStart < (checkMatchIndex - 2):
                        self.Find5PlusByteMatches((currentFindLength + 1), byteNMatchesIndexStart, (checkMatchIndex - 1), byteNM1MatchesIndexStart, not flipped, WordMatches, ByteMatches, byteNMatches)

                    byteNMatchesIndexStart = checkMatchIndex
                    prevByte = curByte

                prevUncompressedIndex = curUncompressedIndex

            if (byteNMatchesIndexEnd - 1) > byteNMatchesIndexStart:
                flipped = not flipped
                if flipped:
                    FlipperMatches1 = WordMatches
                    FlipperMatches2 = ByteMatches
                else:
                    FlipperMatches1 = ByteMatches
                    FlipperMatches2 = WordMatches

                byteNM2MatchesIndexStart = byteNM1MatchesIndexStart
                byteNM1MatchesIndexStart = byteNMatchesIndexStart
                byteNM1MatchesIndexEnd = byteNMatchesIndexEnd

                currentFindLength += 1
            else:
                break

    def Find4ByteMatches(self, byte3MatchesIndexStart, byte3MatchesIndexEnd, wordMatchesIndexStart, WordMatches, ByteMatches):
        byteNMatches = [0x00000000] * 0x100
        byte4Matches =  [0x00000000] * 0x100

        if byte3MatchesIndexStart != byte3MatchesIndexEnd:
            wordMatchesIndex = byte3MatchesIndexStart
            while wordMatchesIndex <= byte3MatchesIndexEnd:
                byte4Matches[self.uncompressed_data[(ByteMatches[wordMatchesIndex] + 3)]] += 1
                wordMatchesIndex += 1

            totalCount = 0
            for byte in range(0x100):
                totalCount += byte4Matches[byte]
                byte4Matches[byte] = totalCount

            wordMatchesIndex = byte3MatchesIndexEnd
            while byte3MatchesIndexStart <= wordMatchesIndex:
                uncompressed_index = ByteMatches[wordMatchesIndex]

                byte4Matches[self.uncompressed_data[(uncompressed_index + 3)]] -= 1
                WordMatches[wordMatchesIndexStart + byte4Matches[self.uncompressed_data[(uncompressed_index + 3)]]] = uncompressed_index

                wordMatchesIndex -= 1

            byte4MatchesIndexStart = wordMatchesIndexStart
            byte4MatchesIndexEnd = (wordMatchesIndexStart + (byte3MatchesIndexEnd - byte3MatchesIndexStart)) & 0xffffffff
            prevUncompressedIndex = WordMatches[wordMatchesIndexStart]
            prevByte = self.uncompressed_data[prevUncompressedIndex + 3]
            for checkMatchIndex in range((wordMatchesIndexStart + 1) & 0xffffffff, byte4MatchesIndexEnd + 1):
                curUncompressedIndex = WordMatches[checkMatchIndex]
                curByte = self.uncompressed_data[(curUncompressedIndex + 3)]

                if prevByte == curByte:
                    matchDiff = (curUncompressedIndex - prevUncompressedIndex) & 0xffffffff

                    if matchDiff < self.OffsetChecks[1][0]:
                        self.CloseMatchesNOffsetDiffs[curUncompressedIndex] = matchDiff + self.OffsetChecks[1][3]
                    elif matchDiff < self.OffsetChecks[2][0]:
                        self.DistantMatchesNLengths[curUncompressedIndex] = matchDiff + self.OffsetChecks[2][3]
                    elif matchDiff < self.OffsetChecks[3][0]:
                        self.DistantMatchesNLengths[curUncompressedIndex] |= (matchDiff + self.OffsetChecks[3][3]) << 0x0f
                    elif matchDiff < self.OffsetChecks[4][0]:
                        self.DistantMatchesNLengths[curUncompressedIndex] = (self.DistantMatchesNLengths[curUncompressedIndex] & 0xfffffffff) | ((matchDiff + self.OffsetChecks[4][3]) << 0x2B)
                else:
                    if byte4MatchesIndexStart < (checkMatchIndex - 2):
                        self.Find5PlusByteMatches(5, byte4MatchesIndexStart, (checkMatchIndex - 1), byte3MatchesIndexStart, False, WordMatches, ByteMatches, byteNMatches)

                    byte4MatchesIndexStart = checkMatchIndex
                    prevByte = curByte

                prevUncompressedIndex = curUncompressedIndex

            if byte4MatchesIndexStart < (byte4MatchesIndexEnd - 1):
                self.Find5PlusByteMatches(5, byte4MatchesIndexStart, byte4MatchesIndexEnd, byte3MatchesIndexStart, False, WordMatches, ByteMatches, byteNMatches)
    
    def Find3ByteMatches(self, wordMatchesIndexStart, wordMatchesIndexEnd, WordMatches, ByteMatches):
        byte3Matches = [0x00000000] * 0x100

        if wordMatchesIndexStart != wordMatchesIndexEnd:
            wordMatchesIndex = wordMatchesIndexStart
            while wordMatchesIndex <= wordMatchesIndexEnd:
                byte3Matches[self.uncompressed_data[(WordMatches[wordMatchesIndex] + 2)]] += 1
                wordMatchesIndex += 1

            totalCount = 0
            for byte in range(0x100):
                totalCount += byte3Matches[byte]
                byte3Matches[byte] = totalCount

            wordMatchesIndex = wordMatchesIndexEnd
            while wordMatchesIndexStart <= wordMatchesIndex:
                uncompressed_index = WordMatches[wordMatchesIndex]
                byte = self.uncompressed_data[(uncompressed_index + 2)]

                byte3Matches[byte] -= 1
                ByteMatches[byte3Matches[byte]] = uncompressed_index
                self.DistantMatchesNLengths[uncompressed_index] = 0

                wordMatchesIndex -= 1
            
            byte3MatchesIndexStart = 0
            byte3MatchesIndexEnd = (wordMatchesIndexEnd - wordMatchesIndexStart)
            prevUncompressedIndex = ByteMatches[0]
            prevByte = self.uncompressed_data[prevUncompressedIndex + 2]
            for checkMatchIndex in range(1, byte3MatchesIndexEnd + 1):
                curUncompressedIndex = ByteMatches[checkMatchIndex]

                curByte = self.uncompressed_data[(curUncompressedIndex + 2)]

                if prevByte == curByte:
                    matchDiff = (curUncompressedIndex - prevUncompressedIndex) & 0xffffffff

                    if matchDiff < self.OffsetChecks[1][0]:
                        self.CloseMatchesNOffsetDiffs[curUncompressedIndex] = matchDiff + self.OffsetChecks[1][3]
                    elif matchDiff < self.OffsetChecks[2][0]:
                        self.DistantMatchesNLengths[curUncompressedIndex] = matchDiff + self.OffsetChecks[2][3]
                else:
                    self.Find4ByteMatches(byte3MatchesIndexStart, (checkMatchIndex - 1), wordMatchesIndexStart, WordMatches, ByteMatches)

                    byte3MatchesIndexStart = checkMatchIndex
                    prevByte = curByte

                prevUncompressedIndex = curUncompressedIndex

            self.Find4ByteMatches(byte3MatchesIndexStart, byte3MatchesIndexEnd, wordMatchesIndexStart, WordMatches, ByteMatches)
        else:
            self.DistantMatchesNLengths[WordMatches[wordMatchesIndexStart]] = 0

    def FindMatches(self):
        WordMatches = [0x00000000] * (self.uncompressed_length)
        WordCount = [0x00000000] * 0x10000

        uncompressed_index = 0
        while (self.uncompressed_length-1) > uncompressed_index:
            word = int.from_bytes(self.uncompressed_data[uncompressed_index:uncompressed_index+2], signed=False, byteorder='little')
            WordCount[word] += 1
            uncompressed_index += 1

        totalCount = 0
        highCount = 0
        for word in range(len(WordCount)):
            if WordCount[word] > highCount:
                highCount = WordCount[word]
            totalCount += WordCount[word]
            WordCount[word] = totalCount

        ByteMatches = [0x00000000] * ((highCount + 1))

        uncompressed_index = (self.uncompressed_length - 1)
        while uncompressed_index > 0:
            uncompressed_index -= 1
            word = int.from_bytes(self.uncompressed_data[uncompressed_index:uncompressed_index+2], signed=False, byteorder='little')
            WordCount[word] -= 1
            WordMatches[WordCount[word]] = uncompressed_index


        self.CloseMatchesNOffsetDiffs[WordMatches[0]] = 0

        wordMatchesIndexStart = 0
        wordMatchesEnd = (len(WordMatches) - 1)
        prevUncompressedIndex = WordMatches[0]
        prevWord = int.from_bytes(self.uncompressed_data[prevUncompressedIndex:prevUncompressedIndex+2], signed=False, byteorder='little')
        for checkMatchIndex in range(1, wordMatchesEnd):
            curUncompressedIndex = WordMatches[checkMatchIndex]
            curWord = int.from_bytes(self.uncompressed_data[curUncompressedIndex:curUncompressedIndex+2], signed=False, byteorder='little')

            if prevWord == curWord:
                matchDiff = (curUncompressedIndex - prevUncompressedIndex) & 0xffffffff

                if matchDiff < self.OffsetChecks[1][0]:
                    self.CloseMatchesNOffsetDiffs[curUncompressedIndex] = matchDiff + self.OffsetChecks[1][4]
                else:
                    self.CloseMatchesNOffsetDiffs[curUncompressedIndex] = 0
            else:
                self.CloseMatchesNOffsetDiffs[curUncompressedIndex] = 0

                self.Find3ByteMatches(wordMatchesIndexStart, (checkMatchIndex - 1), WordMatches, ByteMatches)

                wordMatchesIndexStart = checkMatchIndex
                prevWord = curWord
            
            prevUncompressedIndex = curUncompressedIndex

        self.Find3ByteMatches(wordMatchesIndexStart, (wordMatchesEnd - 1), WordMatches, ByteMatches)
    
    def FindOffsetMatchScore(self, best_match_offset_diff, match_length, copy_offset_match = False, uncompressed_index = -1):
        if copy_offset_match and len(self.BitWeights) >= 8:
            if len(self.EncoderConfig) > 1 and self.uncompressed_index > self.EncoderConfig[1][0]:
                return self.BitWeights[7][min(match_length, 9)]
            else:
                return self.BitWeights[6][min(match_length, 9)]
        else:
            if best_match_offset_diff < self.OffsetChecks[1][0]:
                return self.BitWeights[1][min(match_length, 9)]
            elif best_match_offset_diff < self.OffsetChecks[2][0]:
                return self.BitWeights[2][min(match_length, 9)]
            elif best_match_offset_diff < self.OffsetChecks[3][0]:
                return self.BitWeights[3][min(match_length, 9)]
            elif best_match_offset_diff < self.OffsetChecks[4][0]:
                return self.BitWeights[4][min(match_length, 9)]
            else:
                return 0xff

    def FindMatchLength(self, currentIndex, matchIndex, maxMatchLength):
        distanceToEnd = self.uncompressed_length - currentIndex

        if maxMatchLength > distanceToEnd:
            maxMatchLength = distanceToEnd

        matchLength = 0
        while self.uncompressed_data[(currentIndex)] == self.uncompressed_data[(matchIndex)]:
            matchIndex += 1
            currentIndex += 1

            if matchLength >= maxMatchLength:
                return matchLength

            matchLength += 1

        return matchLength

    def start_new_flag_byte(self):
        self.compressed_flag_index = self.compressed_index
        self.compressed_data[self.compressed_flag_index] = 0
        self.compressed_index += 1
        self.flag_bit_index = 0

    def write_flag_bit(self, bit_value):
        self.flag_bit_index += 1

        if self.flag_bit_index >= 8:
            self.start_new_flag_byte()

        if bit_value or bit_value == 1:
            bef = self.compressed_data[self.compressed_flag_index]
            self.compressed_data[self.compressed_flag_index] |= (1 << self.flag_bit_index) & 0xFF

    def RankMatches(self):
        WeightProfileRing    = [0x0000000000000000] * self.WEIGHT_PROFILE_SIZE
        WeightProfileRing[(self.uncompressed_length - 0) & (self.WEIGHT_PROFILE_SIZE - 1)] = self.BitWeights[0][1]
        WeightProfileRing[(self.uncompressed_length - 1) & (self.WEIGHT_PROFILE_SIZE - 1)] = self.BitWeights[0][0]

        self.DistantMatchesNLengths[len(self.DistantMatchesNLengths) - 1] = 1
        self.CloseMatchesNOffsetDiffs[len(self.CloseMatchesNOffsetDiffs) - 1] = 1

        best_match_offset_diff = 0
        uncompressed_index = (self.uncompressed_length - 1)
        prev_match_offset_diff = -1
        copy_check_max_index = uncompressed_index - self.MAX_LENGTH
        while 0 <= uncompressed_index:
            # Default: Level 0 (no match, copy byte)
            best_position_weight = WeightProfileRing[(uncompressed_index + 1) & (self.WEIGHT_PROFILE_SIZE - 1)] + self.BitWeights[0][0]
            best_match_length = 0x01

            # Level 1 (match offset less than 0x101 away)
            if (self.CloseMatchesNOffsetDiffs[uncompressed_index] & self.OffsetChecks[1][5]) != 0:
                current_match_offset_diff = (self.CloseMatchesNOffsetDiffs[uncompressed_index] & self.OffsetChecks[1][4]) + self.OffsetChecks[1][2]
                max_length = self.FindMatchLength(uncompressed_index, (uncompressed_index - current_match_offset_diff), self.MAX_LENGTH)
                start_length = self.MAX_LENGTH if (max_length == self.MAX_LENGTH) else 0x02

                if max_length >= 0x02:
                    after_match_offset = uncompressed_index + start_length
                    current_length = start_length

                    while current_length <= max_length:
                        current_bit_weight = self.BitWeights[1][min(current_length, 9)]
                        current_position_weight = (WeightProfileRing[after_match_offset & (self.WEIGHT_PROFILE_SIZE - 1)] + current_bit_weight)

                        if (current_position_weight < best_position_weight):
                            best_position_weight = current_position_weight
                            best_match_offset_diff = current_match_offset_diff
                            best_match_length = current_length

                        current_length += 1
                        after_match_offset += 1


            # Level 2 (match offset less than 0x1101 away)
            if (self.DistantMatchesNLengths[uncompressed_index] & self.OffsetChecks[2][5]) != 0:
                current_match_offset_diff = (self.DistantMatchesNLengths[uncompressed_index] & self.OffsetChecks[2][4]) + self.OffsetChecks[2][2]
                max_length = self.FindMatchLength(uncompressed_index, (uncompressed_index - current_match_offset_diff), self.MAX_LENGTH)
                start_length = self.MAX_LENGTH if (max_length == self.MAX_LENGTH) else 0x03

                if max_length >= 0x03:
                    after_match_offset = uncompressed_index + start_length
                    current_length = start_length

                    while current_length <= max_length:
                        current_bit_weight = self.BitWeights[2][min(current_length, 9)]
                        current_position_weight = (WeightProfileRing[after_match_offset & (self.WEIGHT_PROFILE_SIZE - 1)] + current_bit_weight)

                        if (current_position_weight < best_position_weight):
                            best_position_weight = current_position_weight
                            best_match_offset_diff = current_match_offset_diff
                            best_match_length = current_length

                        current_length += 1
                        after_match_offset += 1

            # Level 3 (match offset less than 0x11101 away)
            if ((self.DistantMatchesNLengths[uncompressed_index] >> 0x0f) & self.OffsetChecks[3][5]) != 0:
                current_match_offset_diff = ((self.DistantMatchesNLengths[uncompressed_index] >> 0x0f) + self.OffsetChecks[3][2]) & self.OffsetChecks[3][4]
                max_length = self.FindMatchLength(uncompressed_index, (uncompressed_index - current_match_offset_diff), self.MAX_LENGTH)
                start_length = self.MAX_LENGTH if (max_length == self.MAX_LENGTH) else 0x04
                
                if max_length >= 0x04:
                    after_match_offset = uncompressed_index + start_length
                    current_length = start_length

                    while current_length <= max_length:
                        current_bit_weight = self.BitWeights[3][min(current_length, 9)]
                        current_position_weight = (WeightProfileRing[after_match_offset & (self.WEIGHT_PROFILE_SIZE - 1)] + current_bit_weight)

                        if (current_position_weight < best_position_weight):
                            best_position_weight = current_position_weight
                            best_match_offset_diff = current_match_offset_diff
                            best_match_length = current_length

                        current_length += 1
                        after_match_offset += 1

            # Level 4 (match offset less than 0x111101 away; matched in Find4ByteMatches)
            if ((self.DistantMatchesNLengths[uncompressed_index] >> 0x2B) & self.OffsetChecks[4][5]) != 0:
                current_match_offset_diff = ((self.DistantMatchesNLengths[uncompressed_index] >> 0x2B) + self.OffsetChecks[4][2]) & self.OffsetChecks[4][4]
                max_length = self.FindMatchLength(uncompressed_index, (uncompressed_index - current_match_offset_diff), self.MAX_LENGTH)
                start_length = self.MAX_LENGTH if (max_length == self.MAX_LENGTH) else 0x04
                
                if max_length >= 0x04:
                    after_match_offset = uncompressed_index + start_length
                    current_length = start_length

                    while current_length <= max_length:
                        current_bit_weight = self.BitWeights[4][min(current_length, 9)]
                        current_position_weight = (WeightProfileRing[after_match_offset & (self.WEIGHT_PROFILE_SIZE - 1)] + current_bit_weight)

                        if (current_position_weight < best_position_weight):
                            best_position_weight = current_position_weight
                            best_match_offset_diff = current_match_offset_diff
                            best_match_length = current_length

                        current_length += 1
                        after_match_offset += 1

            # Level 5 (match offset less than 0x111101 away; matched in Find5PlusByteMatches)
            if ((self.DistantMatchesNLengths[uncompressed_index] >> 0x47) & self.OffsetChecks[4][5]) != 0:
                current_match_offset_diff = ((self.DistantMatchesNLengths[uncompressed_index] >> 0x47) + self.OffsetChecks[4][2]) & self.OffsetChecks[4][4]
                max_length = self.FindMatchLength(uncompressed_index, (uncompressed_index - current_match_offset_diff), self.MAX_LENGTH)
                start_length = self.MAX_LENGTH if (max_length == self.MAX_LENGTH) else 0x04
                
                if max_length >= 0x04:
                    after_match_offset = uncompressed_index + start_length
                    current_length = start_length

                    while current_length <= max_length:
                        current_bit_weight = self.BitWeights[5][min(current_length, 9)]
                        current_position_weight = (WeightProfileRing[after_match_offset & (self.WEIGHT_PROFILE_SIZE - 1)] + current_bit_weight)

                        if (current_position_weight < best_position_weight):
                            best_position_weight = current_position_weight
                            best_match_offset_diff = current_match_offset_diff
                            best_match_length = current_length

                        current_length += 1
                        after_match_offset += 1

            WeightProfileRing[uncompressed_index & (self.WEIGHT_PROFILE_SIZE - 1)] = best_position_weight
            self.CloseMatchesNOffsetDiffs[uncompressed_index] = best_match_offset_diff
            self.DistantMatchesNLengths[uncompressed_index] = best_match_length

            uncompressed_index -= 1

    def EncodeMatches(self):
        self.compressed_data = bytearray(self.uncompressed_length)

        csize = self.uncompressed_length.to_bytes(4, "little")
        self.compressed_data[0] = csize[0]
        self.compressed_data[1] = csize[1]
        self.compressed_data[2] = csize[2]
        self.compressed_data[3] = csize[3]
        self.compressed_index += 4

        self.RankMatches()

        self.start_new_flag_byte()
        self.uncompressed_index = 0
        last_block_uncompressed_position = self.uncompressed_index
        last_block_compressed_position = self.compressed_index
        last_block_flag_position = self.compressed_flag_index
        last_block_flag = self.compressed_data[self.compressed_flag_index]
        last_block_flag_bit_index = self.flag_bit_index
        last_block_match_offset_diff = -1
        last_block_match_length = -1
        last_match_offset_diff = -1
        last_match_length = -1
        while self.uncompressed_index < self.uncompressed_length:
            if (self.uncompressed_index - last_block_uncompressed_position) >= self.BLOCK_SIZE:
                if (self.compressed_index - last_block_compressed_position) > self.BLOCK_SIZE:
                    self.compressed_index = last_block_compressed_position
                    self.compressed_flag_index = last_block_flag_position
                    self.compressed_data[self.compressed_flag_index] = last_block_flag
                    self.flag_bit_index = last_block_flag_bit_index
                    self.uncompressed_index = last_block_uncompressed_position
                    last_match_offset_diff = last_block_match_offset_diff
                    last_match_length = last_block_match_length

                    self.write_flag_bit(1)

                    while self.uncompressed_index < (last_block_uncompressed_position + self.BLOCK_SIZE):
                        self.compressed_data[self.compressed_index + 0] = self.uncompressed_data[self.uncompressed_index + 0]
                        self.compressed_data[self.compressed_index + 1] = self.uncompressed_data[self.uncompressed_index + 1]
                        self.compressed_data[self.compressed_index + 2] = self.uncompressed_data[self.uncompressed_index + 2]
                        self.compressed_data[self.compressed_index + 3] = self.uncompressed_data[self.uncompressed_index + 3]

                        self.compressed_index += 4
                        self.uncompressed_index += 4

                last_block_uncompressed_position = self.uncompressed_index
                last_block_compressed_position = self.compressed_index
                last_block_flag_position = self.compressed_flag_index
                last_block_flag = self.compressed_data[self.compressed_flag_index]
                last_block_flag_bit_index = self.flag_bit_index
                last_block_match_offset_diff = last_match_offset_diff
                last_block_match_length = last_match_length

                self.write_flag_bit(0)

            match_length = self.DistantMatchesNLengths[self.uncompressed_index]
            match_offset_diff = self.CloseMatchesNOffsetDiffs[self.uncompressed_index]

            EncoderConfig = self.EncoderConfig[0][2]
            can_copy_prev_offset = self.EncoderConfig[0][1]
            if len(self.EncoderConfig) > 1 and self.uncompressed_index > self.EncoderConfig[1][0]:
                EncoderConfig = self.EncoderConfig[1][2]
                can_copy_prev_offset = self.EncoderConfig[1][1]

            if can_copy_prev_offset:
                if match_offset_diff > 0 and match_offset_diff != last_match_offset_diff:
                    copy_offset_length = self.FindMatchLength(self.uncompressed_index, (self.uncompressed_index - last_match_offset_diff), self.MAX_LENGTH)

                    if copy_offset_length >= 3:
                        if copy_offset_length >= match_length:
                            match_offset_diff = last_match_offset_diff
                            match_length = copy_offset_length
                        else:
                            current_bit_weight = self.FindOffsetMatchScore(match_offset_diff, match_length)
                            copy_offset_bit_weight = self.FindOffsetMatchScore(match_offset_diff, copy_offset_length, True, self.uncompressed_index)

                            if (current_bit_weight - copy_offset_bit_weight) > ((match_length - copy_offset_length) * 8):
                                match_offset_diff = last_match_offset_diff
                                match_length = copy_offset_length

            if match_length == 1:
                self.write_flag_bit(1)
                self.compressed_data[self.compressed_index] = self.uncompressed_data[self.uncompressed_index]
                self.compressed_index += 1
                self.uncompressed_index += 1
            else:
                self.write_flag_bit(0)

                encoded_offset_bits = EncoderConfig[0][0][0]
                cpy_prv_offset_bits = EncoderConfig[0][0][2]

                if match_length == 2:
                    encoded_offset_bits = EncoderConfig[1][0][0]
                    encoded_match_offset = match_offset_diff + EncoderConfig[1][0][1]
                    cpy_prv_offset_bits = EncoderConfig[1][0][2]
                elif match_length == 3:
                    if match_offset_diff > self.OffsetChecks[1][1] or match_offset_diff == 0x101:#(self.version == LZJ_VERSION.VERSION1 and match_offset_diff == 0x101):
                        encoded_offset_bits = EncoderConfig[2][1][0]
                        encoded_match_offset = match_offset_diff + EncoderConfig[2][1][1]
                        cpy_prv_offset_bits = EncoderConfig[2][1][2]
                    else:
                        encoded_offset_bits = EncoderConfig[1][1][0]
                        encoded_match_offset = match_offset_diff + EncoderConfig[1][1][1]
                        cpy_prv_offset_bits = EncoderConfig[1][1][2]
                else:
                    if match_length == 4:
                        self.write_flag_bit(0)
                        self.write_flag_bit(1)
                    else:
                        self.write_flag_bit(1)

                        if match_length >= 9:
                            self.write_flag_bit(1)
                            
                            self.compressed_data[self.compressed_index] = (match_length - 0x09) & 0xFF
                            self.compressed_index += 1
                        else:
                            self.write_flag_bit(0)
                            self.write_flag_bit((((match_length - 1) & 2) != 0))
                            self.write_flag_bit((((match_length - 1) & 1) != 0))

                    if match_offset_diff >= self.OffsetChecks[1][1]:
                        if match_offset_diff >= self.OffsetChecks[3][1]:
                            if match_length >= 5:
                                encoded_offset_bits = EncoderConfig[4][3][0]
                                encoded_match_offset = match_offset_diff + EncoderConfig[4][3][1]
                                cpy_prv_offset_bits = EncoderConfig[4][3][2]
                            else:
                                encoded_offset_bits = EncoderConfig[4][2][0]
                                encoded_match_offset = match_offset_diff + EncoderConfig[4][2][1]
                                cpy_prv_offset_bits = EncoderConfig[4][2][2]
                        else:
                            if match_offset_diff >= self.OffsetChecks[2][1]:
                                if match_length >= 5:
                                    encoded_offset_bits = EncoderConfig[3][3][0]
                                    encoded_match_offset = match_offset_diff + EncoderConfig[3][3][1]
                                    cpy_prv_offset_bits = EncoderConfig[3][3][2]
                                else:
                                    encoded_offset_bits = EncoderConfig[3][2][0]
                                    encoded_match_offset = match_offset_diff + EncoderConfig[3][2][1]
                                    cpy_prv_offset_bits = EncoderConfig[3][2][2]
                            else:
                                if match_length >= 5:
                                    encoded_offset_bits = EncoderConfig[2][3][0]
                                    encoded_match_offset = match_offset_diff + EncoderConfig[2][3][1]
                                    cpy_prv_offset_bits = EncoderConfig[2][3][2]
                                else:
                                    encoded_offset_bits = EncoderConfig[2][2][0]
                                    encoded_match_offset = match_offset_diff + EncoderConfig[2][2][1]
                                    cpy_prv_offset_bits = EncoderConfig[2][2][2]
                    else:
                        if match_length >= 5:
                            encoded_offset_bits = EncoderConfig[1][3][0]
                            encoded_match_offset = match_offset_diff + EncoderConfig[1][3][1]
                            cpy_prv_offset_bits = EncoderConfig[1][3][2]
                        else:
                            encoded_offset_bits = EncoderConfig[1][2][0]
                            encoded_match_offset = match_offset_diff + EncoderConfig[1][2][1]
                            cpy_prv_offset_bits = EncoderConfig[1][2][2]

                encoded_match = (encoded_match_offset << (0x20 - encoded_offset_bits)) & 0xffffffffffffffff # LZJ "64"

                if can_copy_prev_offset and cpy_prv_offset_bits > 0x00 and match_length >= 3 and match_offset_diff == last_match_offset_diff:
                    if match_length == 3:
                        self.write_flag_bit(0)
                        self.write_flag_bit(0)
                        self.write_flag_bit(1)
                        self.write_flag_bit(1)
                    elif match_length == 4:
                        self.write_flag_bit(0)
                        self.write_flag_bit(1)
                    elif match_length >= 5:
                        self.write_flag_bit(1)
                        self.write_flag_bit(1)

                    while cpy_prv_offset_bits > 0:
                        self.write_flag_bit(0)

                        cpy_prv_offset_bits -= 1
                else:
                    while encoded_offset_bits > 0:
                        self.write_flag_bit((encoded_match & 0x80000000) != 0)

                        encoded_match <<= 1
                        encoded_offset_bits -= 1

                last_match_offset_diff = match_offset_diff
                last_match_length = match_length

                self.uncompressed_index += match_length


        self.compressed_data = self.compressed_data[0:self.compressed_index]

    def Lzj_Compress(self, uncompressed_data):
        if self.version == LZJ_VERSION.VERSIONX:
            return uncompressed_data
        else:
            self.uncompressed_data = bytearray(uncompressed_data)
            self.uncompressed_length = len(uncompressed_data)

            for i in range(0x108):
                self.uncompressed_data.append(0x00)

            self.CloseMatchesNOffsetDiffs = [0x0000000000000000] * (self.uncompressed_length)
            self.DistantMatchesNLengths = [0x0000000000000000] * (self.uncompressed_length)

            self.FindMatches()
            self.EncodeMatches()

            return self.compressed_data

    def read_flag_bit(self):
        prev_bit = ((self.flag & 1) == 1)

        self.flag >>= 1
        self.flag_bit_index -= 1

        if self.flag_bit_index <= 0:
            self.flag_bit_index = 8 
            self.flag = self.compressed_data[self.compressed_index] if self.compressed_index < self.compressed_length else 0x00
            self.compressed_index += 1

        return prev_bit

    def _add_byte(self, byte):
        self.uncompressed_data[self.uncompressed_index] = byte
        self.uncompressed_index += 1

    def _copy_bytes(self, size):
        for p in range(size):
            self._add_byte(self.compressed_data[self.compressed_index])
            self.compressed_index += 1

    def DecodeLiteral(self, match_length):
        block_index = 0

        can_stop_early = (self.version == LZJ_VERSION.VERSION2 and self.match_block_index_length == 0x0c)
        while self.match_block_index_length != 0:
            self.read_flag_bit()

            block_index = (block_index * 2) + (self.flag & 1)
            self.match_block_index_length -= 1

            if self.match_block_index_length <= 0x08 and can_stop_early:
                if block_index != 0:
                    can_stop_early = False
                else:
                    break

        if not can_stop_early:
            self.match_offset_diff = (self.match_block_position + block_index)

        match_index = self.uncompressed_index - self.match_offset_diff

        if self.uncompressed_length < (match_index + match_length):
            match_length = self.uncompressed_length - match_index
        elif match_index > self.uncompressed_index:
            print("BORKED [" + hex(match_index) + " > " + hex(self.uncompressed_index) + "]! Returning, stopped at offset " + hex(self.compressed_index))

            return False
        elif match_index < 0x00:
            print("BORKED [match_index=" + hex(match_index) + " < 0x00, match_offset_diff=" + hex(self.match_offset_diff) + ", uncompressed_index=" + hex(self.uncompressed_index) + "]! Returning, stopped at offset " + hex(self.compressed_index))

            return False

        while match_length != 0:
            self._add_byte(self.uncompressed_data[match_index])
            match_index += 1

            match_length -= 1

        return True

    def Lzj_Expand(self, compressed_data):
        self.neat = {}

        if self.version == LZJ_VERSION.VERSIONX:
            return compressed_data
        else:
            self.compressed_data = compressed_data
            self.compressed_length = len(compressed_data)

            self.uncompressed_length = int.from_bytes(compressed_data[0:4], "little")
            self.uncompressed_data = bytearray(self.uncompressed_length)
            self.compressed_index += 4

            match_block_adder = self.BLOCK_SIZE
            if self.version == LZJ_VERSION.VERSION2:
                match_block_adder = 0
            else:
                match_block_adder = self.BLOCK_SIZE

            while self.uncompressed_length > self.uncompressed_index:
                match_length = 0x00
                self.read_flag_bit() # read bit 1

                if self.uncompressed_index >= self.next_block_position:
                    self.next_block_position = self.uncompressed_index + self.BLOCK_SIZE

                    if (self.flag & 1) == 1: # check bit 1
                        self._copy_bytes(self.BLOCK_SIZE)

                elif (self.flag & 1) == 1: # check bit 1
                    self._copy_bytes(1)
                else:
                    self.read_flag_bit() # read bit 2

                    if self.read_flag_bit(): # read bit 3, check bit 2
                        match_length = 0x05

                        if (self.flag & 1) == 1: # check bit 3
                            match_length = compressed_data[self.compressed_index] + 0x09
                            
                            self.compressed_index += 1
                        else:
                            self.read_flag_bit() # read bit 4

                            if (self.flag & 1) == 1: # check bit 4
                                match_length = 0x07

                            self.read_flag_bit() # read bit 5

                            if (self.flag & 1) == 1: # check bit 5
                                match_length += 0x01

                        self.read_flag_bit() # read bit 6

                        if self.read_flag_bit(): # read bit 7, check bit 6
                            if (self.flag & 1) == 1: # check bit 7
                                if self.version != LZJ_VERSION.VERSION2 or self.uncompressed_index > (0x111000 + 0x01):
                                    self.read_flag_bit() # read bit 8

                                    if (self.flag & 1) == 1: # check bit 8
                                        self.match_block_position = match_block_adder + 0x111000 + 0x01
                                        self.match_block_index_length = 0x17
                                    else:
                                        self.match_block_position = match_block_adder + 0x01 ## need this
                                        self.match_block_index_length = 0x0c
                                else:
                                    self.match_block_position = match_block_adder + 0x01
                                    self.match_block_index_length = 0x0c
                            else:
                                self.match_block_position = match_block_adder + 0x11000 + 0x01
                                self.match_block_index_length = 0x14
                        else:
                            if (self.flag & 1) == 1: # check bit 7
                                self.match_block_position = match_block_adder + 0x1000 + 0x01 ## got this
                                self.match_block_index_length = 0x10
                            else:
                                self.match_block_position = 0x01
                                self.match_block_index_length = 0x08
                    else:
                        if self.read_flag_bit(): # read bit 4, check bit 3
                            match_length = 0x04

                            if self.read_flag_bit(): # read bit 5, check bit 4
                                if (self.flag & 1) == 1: # check bit 5
                                    self.match_block_position = match_block_adder + 0x11000 + 0x01
                                    self.match_block_index_length = 0x14
                                else:
                                    self.match_block_position = match_block_adder + 0x1000 + 0x01
                                    self.match_block_index_length = 0x10
                            else:
                                if (self.flag & 1) == 1: # check bit 5
                                    self.match_block_position = match_block_adder + 0x01
                                    self.match_block_index_length = 0x0c
                                else:
                                    self.match_block_position = 0x01
                                    self.match_block_index_length = 0x08
                        else:
                            if (self.flag & 1) == 1: # check bit 4
                                match_length = 0x03

                                self.read_flag_bit() # read bit 5

                                if self.version == LZJ_VERSION.VERSION0:
                                    if (self.flag & 1) == 1: # check bit 5
                                        self.match_block_position = match_block_adder + 0x1000 + 0x01
                                        self.match_block_index_length = 0x10
                                    else:
                                        self.read_flag_bit() # read bit 6

                                        if (self.flag & 1) == 1: # check bit 6
                                            self.match_block_position = match_block_adder + 0x01
                                            self.match_block_index_length = 0x0c
                                        else:
                                            self.match_block_position = 0x01
                                            self.match_block_index_length = 0x08
                                else:
                                    if (self.flag & 1) == 1: # check bit 5
                                        self.match_block_position = match_block_adder + 0x01
                                        self.match_block_index_length = 0x0c
                                    else:
                                        self.match_block_position = 0x01
                                        self.match_block_index_length = 0x08
                            else:
                                match_length = 0x02

                                self.match_block_position = 0x01
                                self.match_block_index_length = 0x08
                    
                    if not self.DecodeLiteral(match_length):
                        break

            return self.uncompressed_data
