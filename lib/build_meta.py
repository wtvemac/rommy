import os
import sys
import tempfile
import ctypes
import math
import struct
import re
from enum import Enum
from lib.lzss import *
from lib.lzj import *
from lib.tea import *

"""
    All integers are big endian.

    Bytes 0x00-0x08[uint64]: Branch instruction. Jumps to the start section (crt0) before main.
                             This is 0x1000000000000000 in BPS and LC2.5 builds since those builds aren't executable until it's decompressed.
    Bytes 0x08-0x0c[uint32]: ROM Code checksum. Calculated by setting this to 0x00000000 and checksumming the data @ offset 0x00 + the code length
    Bytes 0x0c-0x10[uint32]: Build size measured in DWORDs (need to << 2 the value to convert to bytes). This convers the data that needs to loaded into memory.
    Bytes 0x10-0x14[uint32]: Code size measured in DWORDs (need to << 2 the value to convert to bytes). This covers the data that is to be checksummed.
    Bytes 0x14-0x18[uint32]: The build version number.
    Bytes 0x18-0x1c[uint32]: Addess to the .data section in the build.
    Bytes 0x1c-0x20[uint32]: The size of the .data section.
    Bytes 0x20-0x24[uint32]: The size of the .bss section. Builds were compiled using a MIPS-BE ECOFF toolchain. The value of this comes from that.
    Bytes 0x24-0x28[uint32]: The ROMFS start offset. This is "NoFS" in UTV builds. Most of the time this is the address of very end of the build file. The ROMFS is read from the bottom up.
    Bytes 0x28-0x2c[uint32]: In BPS and LC2.5 boxes this is the LZJ version used. Most of the time it's lzj2. lzj0 can be used for no compression. lzj1 seems to be used in older builds.
    Bytes 0x2c-0x30[uint32]: The size of the LZJ compressed data. The data starts at offset 0x200 in the build file.

    On newer original classic builds or LC2 and up:

    Bytes 0x30-0x34[uint32]: The build base offset. This is the addess at byte 0x00 in the build file. You can use this to convert any build address to a file offset.
    Bytes 0x34-0x38[uint32]: Build flags. Used to indicate the type of build (internal, debug, sattelite, cerom)
    Bytes 0x38-0x3c[uint32]: Compressed .data section size. The builds eventually started compressing the .data section with LZSS.
    Bytes 0x3c-0x40[uint32]: Compressed bootrom build address. The LC2 started compressing the bootrom build. The size is seems to be where it starts up until the end of the checksummed data (use the code size to find this).

    - LC2 uses LZSS to compress the bootrom. BPS, LC2.5 and UTV use LZJ1.
    - In LZJ compressed bootroms, the size of the decompressed data is stored as a uint32 at the start of the compressed data.
    - In LC2 builds, the autodisk file table is at the end of the build. You can use the build size to find that.
    - In UTV buils, the CompressFS partition table starts at the end of the build. You can use the build size to find that.
    - The ROMFS section is within the build size so it's loaded into memory, but it is after the build code. Between the code and ROMFS is a bunch of "joeb" padding. I think Joe Britt wrote the tools combine the ROMFS with the approm code.
    - The UTV builds can be further broken down using structures from the WinCE OS. The ROMHDR address is right after the CECE in the build file (or ECEC when in memory).
"""

class OBJECT_TYPE(int, Enum):
    UNKNOWN   = 0
    FILE      = 1
    DIRECTORY = 2

class IMAGE_TYPE(str, Enum):
    UNKNOWN              = 'UNKNOWN'
    VIEWER               = 'VIEWER'
    VIEWER_SCRAMBLED     = 'VIEWER_SCRAMBLED'
    BOX                  = 'BOX'
    COMPRESSED_BOX       = 'COMPRESSED_BOX'
    BUILD_BUGGED         = 'BUILD_BUGGED'
    DREAMCAST            = 'DREAMCAST'
    COMPRESSED_BOOTROM   = 'COMPRESSED_BOOTROM'
    ORIG_CLASSIC_BOX     = 'ORIG_CLASSIC_BOX'
    ORIG_CLASSIC_BOOTROM = 'ORIG_CLASSIC_BOOTROM'
    ULTIMATETV_BOX       = 'ULTIMATETV_BOX'
    ROM_BLOCKS           = 'ROM_BLOCKS'
    
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


class FILE_COMPRESSION(str, Enum):
    UNKNOWN = "UNKNOWN"
    NONE    = "NONE"
    LZPF    = "LZPF"
    LZSS    = "LZSS"
    LZJV1   = "LZJV1"

class build_meta():
    def print_build_info(build_info, prefix = "Level0 Type: "):
        info = prefix + str(build_info["image_type"]) + "\n   "

        infos = []

        if build_info["build_version"] > 0:
            infos.append("Version: " + str(build_info["build_version"]))

        if build_info["build_address"] >= 0:
            infos.append("Base Address: " + hex(build_info["build_address"]))

        if build_info["build_size"] > 0:
            infos.append("Size: " + hex(build_info["build_size"]))

        if build_info["code_size"] > 0 and build_info["image_type"] != IMAGE_TYPE.COMPRESSED_BOX:
            infos.append(".text size: " + hex(build_info["code_size"]))

        if build_info["bootrom_level1_address"] >= 0:
            infos.append("Bootrom Browser Address: " + hex(build_info["bootrom_level1_address"]))

        if build_info["data_address"] > 0 and build_info["image_type"] != IMAGE_TYPE.COMPRESSED_BOX and build_info["image_type"] != IMAGE_TYPE.COMPRESSED_BOOTROM:
            infos.append("'.data' Address: " + hex(build_info["data_address"]) + " [size " + hex(build_info["data_size"]) + (":compressed" if  ((build_info["build_flags"] & 0x01) == 0x01) else "") + "]")

        if build_info["wince_romhdr_address"] > 0:
            infos.append("WinCE ROMHDR Address: " + hex(build_info["wince_romhdr_address"]))

        if build_info["build_flags"] >= 0:
            flags_info = []

            if (build_info["build_flags"] & 0x01) == 0x01:
                flags_info.append("compressed '.data'")

            if (build_info["build_flags"] & 0x02) == 0x02:
                flags_info.append("internal")

            if (build_info["build_flags"] & 0x04) == 0x04:
                flags_info.append("debug")

            if (build_info["build_flags"] & 0x10) == 0x10:
                flags_info.append("cerom")

            if (build_info["build_flags"] & 0x20) == 0x20:
                flags_info.append("satellite")

            infos.append("Flags: " + hex(build_info["build_flags"]) + " [" + ":".join(flags_info) + "]")

        if build_info["romfs_address"] >= 0 and build_info["image_type"] != IMAGE_TYPE.COMPRESSED_BOX:
            infos.append("ROMFS Address: " + hex(build_info["romfs_address"]) + " [size " + hex(build_info["romfs_size"]) + "]")

        if build_info["storage_table_offset"] >= 0:
            infos.append("CompressFS Table Offset: " + hex(build_info["storage_table_offset"]))

        print(info + ", ".join(infos))

    def checksum(data):
        checksum = 0

        data = bytearray(data)

        if (len(data) % 4) != 0:
            for a in range(4 - (len(data) % 4)):
                data.append(0)

        for i in range(0, len(data), 4):
            checksum += ctypes.c_uint32(
                (data[i] << 0x18) +
                (data[i + 1] << 0x10) +
                (data[i + 2] << 0x08) +
                (data[i + 3])
            ).value

        return checksum & 0xffffffff

    def chunked_checksum(data, chunk_size = 4):
        checksum = ctypes.c_uint32(0)

        data = bytearray(data)

        if chunk_size > 1:
            if (len(data) % chunk_size) != 0:
                for a in range(chunk_size - (len(data) % chunk_size)):
                    data.append(0)

        for i in range(0, len(data), chunk_size):
            if chunk_size == 1:
                checksum.value += data[i]
            elif chunk_size == 2:
                checksum.value += (data[i] << 0x08) + (data[i + 1])
            elif chunk_size == 3:
                checksum.value += (data[i] << 0x10) + (data[i + 1] << 0x08) + (data[i + 2])
            elif chunk_size == 4:
                checksum.value += (data[i] << 0x18) + (data[i + 1] << 0x10) + (data[i + 2] << 0x08) + (data[i + 3])

        return checksum.value & 0xffffffff

    def crc32(data, crc = 0xffffffff):
        table = [
            0x00000000, 0x77073096, 0xee0e612c, 0x990951ba,
            0x076dc419, 0x706af48f, 0xe963a535, 0x9e6495a3,
            0x0edb8832, 0x79dcb8a4, 0xe0d5e91e, 0x97d2d988,
            0x09b64c2b, 0x7eb17cbd, 0xe7b82d07, 0x90bf1d91,
            0x1db71064, 0x6ab020f2, 0xf3b97148, 0x84be41de,
            0x1adad47d, 0x6ddde4eb, 0xf4d4b551, 0x83d385c7,
            0x136c9856, 0x646ba8c0, 0xfd62f97a, 0x8a65c9ec,
            0x14015c4f, 0x63066cd9, 0xfa0f3d63, 0x8d080df5,
            0x3b6e20c8, 0x4c69105e, 0xd56041e4, 0xa2677172,
            0x3c03e4d1, 0x4b04d447, 0xd20d85fd, 0xa50ab56b,
            0x35b5a8fa, 0x42b2986c, 0xdbbbc9d6, 0xacbcf940,
            0x32d86ce3, 0x45df5c75, 0xdcd60dcf, 0xabd13d59,
            0x26d930ac, 0x51de003a, 0xc8d75180, 0xbfd06116,
            0x21b4f4b5, 0x56b3c423, 0xcfba9599, 0xb8bda50f,
            0x2802b89e, 0x5f058808, 0xc60cd9b2, 0xb10be924,
            0x2f6f7c87, 0x58684c11, 0xc1611dab, 0xb6662d3d,
            0x76dc4190, 0x01db7106, 0x98d220bc, 0xefd5102a,
            0x71b18589, 0x06b6b51f, 0x9fbfe4a5, 0xe8b8d433,
            0x7807c9a2, 0x0f00f934, 0x9609a88e, 0xe10e9818,
            0x7f6a0dbb, 0x086d3d2d, 0x91646c97, 0xe6635c01,
            0x6b6b51f4, 0x1c6c6162, 0x856530d8, 0xf262004e,
            0x6c0695ed, 0x1b01a57b, 0x8208f4c1, 0xf50fc457,
            0x65b0d9c6, 0x12b7e950, 0x8bbeb8ea, 0xfcb9887c,
            0x62dd1ddf, 0x15da2d49, 0x8cd37cf3, 0xfbd44c65,
            0x4db26158, 0x3ab551ce, 0xa3bc0074, 0xd4bb30e2,
            0x4adfa541, 0x3dd895d7, 0xa4d1c46d, 0xd3d6f4fb,
            0x4369e96a, 0x346ed9fc, 0xad678846, 0xda60b8d0,
            0x44042d73, 0x33031de5, 0xaa0a4c5f, 0xdd0d7cc9,
            0x5005713c, 0x270241aa, 0xbe0b1010, 0xc90c2086,
            0x5768b525, 0x206f85b3, 0xb966d409, 0xce61e49f,
            0x5edef90e, 0x29d9c998, 0xb0d09822, 0xc7d7a8b4,
            0x59b33d17, 0x2eb40d81, 0xb7bd5c3b, 0xc0ba6cad,
            0xedb88320, 0x9abfb3b6, 0x03b6e20c, 0x74b1d29a,
            0xead54739, 0x9dd277af, 0x04db2615, 0x73dc1683,
            0xe3630b12, 0x94643b84, 0x0d6d6a3e, 0x7a6a5aa8,
            0xe40ecf0b, 0x9309ff9d, 0x0a00ae27, 0x7d079eb1,
            0xf00f9344, 0x8708a3d2, 0x1e01f268, 0x6906c2fe,
            0xf762575d, 0x806567cb, 0x196c3671, 0x6e6b06e7,
            0xfed41b76, 0x89d32be0, 0x10da7a5a, 0x67dd4acc,
            0xf9b9df6f, 0x8ebeeff9, 0x17b7be43, 0x60b08ed5,
            0xd6d6a3e8, 0xa1d1937e, 0x38d8c2c4, 0x4fdff252,
            0xd1bb67f1, 0xa6bc5767, 0x3fb506dd, 0x48b2364b,
            0xd80d2bda, 0xaf0a1b4c, 0x36034af6, 0x41047a60,
            0xdf60efc3, 0xa867df55, 0x316e8eef, 0x4669be79,
            0xcb61b38c, 0xbc66831a, 0x256fd2a0, 0x5268e236,
            0xcc0c7795, 0xbb0b4703, 0x220216b9, 0x5505262f,
            0xc5ba3bbe, 0xb2bd0b28, 0x2bb45a92, 0x5cb36a04,
            0xc2d7ffa7, 0xb5d0cf31, 0x2cd99e8b, 0x5bdeae1d,
            0x9b64c2b0, 0xec63f226, 0x756aa39c, 0x026d930a,
            0x9c0906a9, 0xeb0e363f, 0x72076785, 0x05005713,
            0x95bf4a82, 0xe2b87a14, 0x7bb12bae, 0x0cb61b38,
            0x92d28e9b, 0xe5d5be0d, 0x7cdcefb7, 0x0bdbdf21,
            0x86d3d2d4, 0xf1d4e242, 0x68ddb3f8, 0x1fda836e,
            0x81be16cd, 0xf6b9265b, 0x6fb077e1, 0x18b74777,
            0x88085ae6, 0xff0f6a70, 0x66063bca, 0x11010b5c,
            0x8f659eff, 0xf862ae69, 0x616bffd3, 0x166ccf45,
            0xa00ae278, 0xd70dd2ee, 0x4e048354, 0x3903b3c2,
            0xa7672661, 0xd06016f7, 0x4969474d, 0x3e6e77db,
            0xaed16a4a, 0xd9d65adc, 0x40df0b66, 0x37d83bf0,
            0xa9bcae53, 0xdebb9ec5, 0x47b2cf7f, 0x30b5ffe9,
            0xbdbdf21c, 0xcabac28a, 0x53b39330, 0x24b4a3a6,
            0xbad03605, 0xcdd70693, 0x54de5729, 0x23d967bf,
            0xb3667a2e, 0xc4614ab8, 0x5d681b02, 0x2a6f2b94,
            0xb40bbe37, 0xc30c8ea1, 0x5a05df1b, 0x2d02ef8d
        ]

        for byte in data:  
            crc = table[(byte ^ crc) & 0xff] ^ (crc >> 8)

        return crc & 0xffffffff

    def align(_bytes, align_to = 0x200):
        alignment_size = align_to - (_bytes % align_to)
        if alignment_size < align_to:
            return alignment_size
        else:
            return 0

    def swap_data(data, swap_bits = 32, start_offset = 0x00, end_offset = 0x00):
        new_data = bytearray(0x00)
        for idx in range(start_offset, end_offset if end_offset > 0 else len(data), 0x02 if swap_bits == 16 else 0x04):
            swap_data = bytearray(0x00)
            if swap_bits == 32:
                swap_data = bytearray(data[idx:(idx + 0x04)])
                swap_data.reverse()
            elif swap_bits == 16:
                swap_data = bytearray(data[idx:(idx + 0x02)])
                swap_data.reverse()
            elif swap_bits == 1632 or swap_bits == 3216:
                _swap_data = bytearray(data[idx:(idx + 0x04)])
                _swap_data.reverse()

                swap_data = bytearray(0x04)
                swap_data[0] = _swap_data[1]
                swap_data[1] = _swap_data[0]
                swap_data[2] = _swap_data[3]
                swap_data[3] = _swap_data[2]
            else:
                swap_data = bytearray(data[idx:(idx + 0x04)])

            new_data += swap_data

        return new_data


    def swap_file_data(in_path, out_path = None, swap_bits = 32, start_offset = 0x00, end_offset = 0x00):
        if out_path == None:
            out_path = tempfile.mktemp()

        with open(in_path, "rb") as f:
            file_start = start_offset

            file_end = 0x00
            if end_offset == 0x00:
                f.seek(0, os.SEEK_END)
                file_end = f.tell()
            else:
                file_end = end_offset

            f.seek(file_start)
            with open(out_path, "wb") as f2:
                for index in range(file_start, file_end, 0x04):
                    data = bytearray(0x00)
                    if swap_bits == 32:
                        data = bytearray(f.read(0x04))
                        data.reverse()
                    elif swap_bits == 32:
                        data = bytearray(f.read(0x02))
                        data.reverse()
                    elif swap_bits == 1632 or swap_bits == 3216:
                        _data = bytearray(f.read(0x04))
                        _data.reverse()

                        data = bytearray(0x04)
                        data[0] = _data[1]
                        data[1] = _data[0]
                        data[2] = _data[3]
                        data[3] = _data[2]
                    else:
                        data = bytearray(f.read(0x04))

                    f2.write(data)
                f2.close()
            f.close()

            return out_path

    def get_data(f, start_offset = 0, read_size = 0):
        data = b''

        f.seek(0, os.SEEK_END)
        data_size = f.tell()

        f.seek(start_offset)
        data = f.read((data_size - start_offset) if read_size == 0 else read_size)

        return bytearray(data)

    def get_file_data(path, start_offset = 0, read_size = 0):
        with open(path, 'rb') as f:
            data = build_meta.get_data(f, start_offset, read_size)

            f.close()

        return data

    def write_object_file(build_info, data, silent = False):
        with open(build_info["out_path"], 'wb') as f:
            f.write(data)

            f.close()

        if build_info["image_type"] == IMAGE_TYPE.BOX or build_info["image_type"] == IMAGE_TYPE.COMPRESSED_BOOTROM or build_info["image_type"] == IMAGE_TYPE.COMPRESSED_BOX or build_info["image_type"] == IMAGE_TYPE.ULTIMATETV_BOX:
            if not silent:
                print("\tWrote ROM to '" + build_info["out_path"] + "'")
        else:
            if not silent:
                print("\tWrote ROMFS to '" + build_info["out_path"] + "'")

    def simplify_size(_bytes):
        prefixes = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
        size_e = int(math.floor(math.log(_bytes, 1024))) if _bytes > 0 else 0
        simplified_size = round(_bytes / math.pow(1024, size_e), 2)

        return str(simplified_size) + prefixes[size_e]

    def natural_sort(l): 
        convert = lambda text: int(text) if text.isdigit() else text.lower() 
        alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)] 
        return sorted(l, key=alphanum_key)

    def is_box_build(image_type):
        box_types = [
            IMAGE_TYPE.BOX,
            IMAGE_TYPE.COMPRESSED_BOX,
            IMAGE_TYPE.COMPRESSED_BOOTROM,
            IMAGE_TYPE.ORIG_CLASSIC_BOX,
            IMAGE_TYPE.ORIG_CLASSIC_BOOTROM
        ]

        return image_type in box_types


    def build_blob(build_info, endian, romfs_blob, data_blob = b'', autodisk_blob = b'', level1_build_blob = b'', level1_lzj_version = None, silent = False):
        AUTODISK_FILEM_BGN_MAGIC = 0x39592841
        AUTODISK_FILEM_END_MAGIC = 0x11993456
        build_info["romfs_address"] -= 8
        
        code_blob = b''
        footer_blob = b''
        romfs_padding = b''
        compressed_level1_build_blob = b''
        next_romfs = b''
        compressed_data_size = 0
        data_size = 0
        code_blob_padding = bytearray(b'')
        source_build_info = None

        romfs_size = len(romfs_blob) - 0x08

        if build_info["source_build_path"] != None:
            source_build_info = build_meta.detect(build_info["source_build_path"])

            level1_build_size = 0
            compressed_level1_build_size = 0
            if build_info["image_type"] == IMAGE_TYPE.COMPRESSED_BOOTROM:
                if level1_build_blob != None and len(level1_build_blob) > 0:
                    if not silent:
                        print("\tPacking botrom image. This could take a while...")

                    compressed_blob = b''
                    if build_info["bootrom_level1_compression"] == FILE_COMPRESSION.LZSS:
                        d = lzss()
                        compressed_blob = d.Lzss_Compress(level1_build_blob)
                    else:
                        d = lzj(LZJ_VERSION.VERSION1)
                        compressed_blob = d.Lzj_Compress(level1_build_blob)

                    if len(compressed_blob) > 0:
                        compressed_level1_build_blob = bytearray(0x10) + compressed_blob

                    compressed_level1_build_size = len(compressed_level1_build_blob)

                    if not silent:
                        print("\tDone compression_ratio=" + str(len(compressed_blob) / len(level1_build_blob)) + "...")
            elif build_info["image_type"] == IMAGE_TYPE.COMPRESSED_BOX:
                if level1_build_blob != None and len(level1_build_blob) >= 0x40:
                    if not silent:
                        print("\tPacking level1 image. This could take a while...")

                    if level1_lzj_version != None:
                        build_info["level1_lzj_version"] = LZJ_VERSION(level1_lzj_version)
                    elif build_info["level1_lzj_version"] == -1:
                        build_info["level1_lzj_version"] = LZJ_VERSION.VERSION2

                    d = lzj(LZJ_VERSION(build_info["level1_lzj_version"]))
                    compressed_blob = d.Lzj_Compress(level1_build_blob)

                    if len(compressed_blob) > 0:
                        compressed_level1_build_blob = compressed_blob
                        compressed_level1_build_blob += bytearray(build_meta.align(len(compressed_blob)))

                        # TODO: add checksum? at end of blob don't know how it's calculated yet

                        compressed_level1_build_blob += bytearray(build_meta.align(0x200 + len(compressed_level1_build_blob), 0x20000))


                    compressed_level1_build_size = len(compressed_level1_build_blob)

                    if not silent:
                        if len(compressed_blob) != len(level1_build_blob):
                            print("\tDone compression_ratio=" + str(len(compressed_blob) / len(level1_build_blob)) + "...")
                        else:
                            print("\tDone")
                else:
                    raise Exception("You are asking to build a compressed box (LC2.5 or BPS) build but haven't provided a valid level1 image. I cant build!")

            if source_build_info != None:
                if not silent:
                    print("\tRetrieving source build data.")

                with open(build_info["source_build_path"], "rb") as s:
                    s.seek(0, os.SEEK_END)
                    file_size = s.tell()

                    s.seek(source_build_info["start_offset"])
                    if build_info["image_type"] == IMAGE_TYPE.COMPRESSED_BOX:
                        if source_build_info["level1_image_offset"] == -1:
                            source_build_info["level1_image_offset"] = 0x200

                        if source_build_info["level1_image_offset"] == 0x200:
                            code_blob = bytearray(s.read(0x40))

                            code_blob += bytearray(source_build_info["level1_image_offset"] - 0x40)
                        else:
                            code_blob = bytearray(s.read(source_build_info["level1_image_offset"]))
                    else:
                        code_blob = bytearray(s.read(source_build_info["code_size"]))

                    if data_blob != None and len(data_blob) > 0 and build_info["image_type"] != IMAGE_TYPE.COMPRESSED_BOX:
                        data_size = len(data_blob)
                        if (source_build_info["build_flags"] & 0x01) == 0x01:
                            d = lzss()
                            data_blob = d.Lzss_Compress(data_blob)

                            compressed_data_size = len(data_blob)

                        code_blob = code_blob[0:source_build_info["data_offset"]] + data_blob + code_blob[(source_build_info["data_offset"] + source_build_info["data_size"]):]

                        code_blob_padding_size = (4 - (len(code_blob) % 4))
                        if code_blob_padding_size < 4:
                            code_blob_padding = b'wtvcd' * max((math.ceil(code_blob_padding_size >> 2) + 1), 1)
                            code_blob_padding = code_blob_padding[0:code_blob_padding_size]

                            code_blob += code_blob_padding

                    s.seek(source_build_info["romfs_offset"] - 0x40)
                    next_romfs = bytearray(s.read(4))

                    if source_build_info["bootrom_level1_offset"] > 0 and compressed_level1_build_size == 0:
                        middle_length = file_size - (source_build_info["code_size"] + (source_build_info["romfs_size"] + 0x08) + source_build_info["footer_size"])

                        s.seek(source_build_info["start_offset"] + source_build_info["code_size"])
                        compressed_level1_build_blob = bytearray(s.read(middle_length))
                        compressed_level1_build_size = len(compressed_level1_build_blob)


                    if autodisk_blob != None and len(autodisk_blob) > 0:
                        footer_blob = autodisk_blob
                    elif build_info["autodisk_offset"] > 0:
                        # Create a blank Autodisk section. This is just in case some builds fail when they expect an autodisk section but we provide none.
                        footer_blob = bytearray(0x400)

                        struct.pack_into(
                            endian + "IIIIII",
                            footer_blob,
                            0x00,
                            AUTODISK_FILEM_BGN_MAGIC,
                            0x00,
                            0x01,
                            0x01,
                            0x400,
                            0x00,
                        )

                        struct.pack_into(
                            endian + "I",
                            footer_blob,
                            0x400 - 0x04,
                            AUTODISK_FILEM_END_MAGIC
                        )
                    elif source_build_info["footer_size"] > 0:
                        # This is most likely an autodisk section that wasn't detected (we should!) or tmpfs data.

                        s.seek(source_build_info["start_offset"] + source_build_info["footer_offset"])
                        footer_blob = bytearray(s.read(file_size - source_build_info["footer_offset"]))


                unpadded_size = len(code_blob) + romfs_size + compressed_level1_build_size
                padding_size = build_info["romfs_address"] - (build_info["build_address"] + unpadded_size)

                if padding_size < 0 and build_info["romfs_address"] > 0:
                    if not silent:
                        print("\t!! ROMFS ADDRESS EXTENDS BEYOND SOURCE.  I WILL EXTEND. THIS LIKELY WONT WORK! Expected ROMFS address=" + hex(build_info["romfs_address"]) + " found ROMFS address=" + hex((build_info["build_address"] + unpadded_size)) + ", difference=" + hex(padding_size))

                    padding_size = 0
                    build_info["romfs_address"] = build_info["build_address"] + unpadded_size
                elif romfs_blob != None and len(romfs_blob) >= 0x08:
                    romfs_padding = b'eMac' * max((math.ceil(padding_size >> 2) + 1), 1)
                    romfs_padding = romfs_padding[0:padding_size]
                else:
                    romfs_padding = b''
            else:
                if not silent:
                    print("\t!! CAN'T USE SOURCE BUILD! UNABLE TO DETECT FORMAT!")


        if len(code_blob) == 0:
            if not silent:
                print("\t!! NO CODE FOR BUILD!")
        else:
            build_size = 0

            if romfs_blob != None and len(romfs_blob) >= 0x08:
                if not silent:
                    print("\tCalculating ROMFS params (size and checksum, next address).")

                dword_romfs_size = ctypes.c_uint32(int(romfs_size >> 2)).value

                if len(romfs_blob) >= 0x38 and len(next_romfs) != 0:
                    next_link_offset = (romfs_size - 0x38)

                    romfs_blob[next_link_offset+0] = next_romfs[0]
                    romfs_blob[next_link_offset+1] = next_romfs[1]
                    romfs_blob[next_link_offset+2] = next_romfs[2]
                    romfs_blob[next_link_offset+3] = next_romfs[3]
                    
                romfs_checksum = build_meta.checksum(romfs_blob)
                struct.pack_into(
                    endian + "II",
                    romfs_blob,
                    romfs_size,
                    dword_romfs_size,
                    romfs_checksum
                )

                build_size = (build_info["romfs_address"] + 8) - build_info["build_address"]

                build_size += build_meta.align(build_size, 0x80000)
            else:
                build_size = file_size

            if not silent:
                print("\tChecking and fixing any build header values.")

            if build_info["image_type"] == IMAGE_TYPE.COMPRESSED_BOX:
                code_blob[0:0x40] = level1_build_blob[0:0x40]

                struct.pack_into(
                    endian + "I",
                    code_blob,
                    0x00,
                    0x10000000
                )

                struct.pack_into(
                    endian + "I",
                    code_blob,
                    0x28,
                    build_info["level1_lzj_version"]
                )
                
                struct.pack_into(
                    endian + "I",
                    code_blob,
                    0x2c,
                    compressed_level1_build_size
                )
            else:
                struct.pack_into(
                    endian + "II",
                    code_blob,
                    0x08,
                    0x00000000,
                    build_size >> 2
                )

                if data_blob != None and len(data_blob) > 0:
                    struct.pack_into(
                        endian + "I",
                        code_blob,
                        0x10,
                        len(code_blob) >> 2
                    )

                    struct.pack_into(
                        endian + "I",
                        code_blob,
                        0x1c,
                        data_size >> 2
                    )
                    struct.pack_into(
                        endian + "I",
                        code_blob,
                        0x38,
                        compressed_data_size
                    )
                    
                code_checksum = build_meta.chunked_checksum(code_blob)
                struct.pack_into(
                    endian + "I",
                    code_blob,
                    0x08,
                    code_checksum
                )

        return code_blob + compressed_level1_build_blob + romfs_padding + romfs_blob + footer_blob

    def romfs_address(build_info, position):
        base_address = build_info["romfs_address"]
        romfs_offset = build_info["romfs_offset"]

        if base_address <= -1:
            base_address = 0xffffffff

        if romfs_offset <= 0:
            romfs_offset = 0xffffffff

        address = position - (romfs_offset - (base_address - 0x08))

        #if build_info["image_type"] == IMAGE_TYPE.BOX:
        #    address += 0x08
        
        return address & 0xffffffff

    def romfs_position(build_info, address):
        base_address = build_info["romfs_address"]

        if ((base_address - address) - 0x08) > build_info["romfs_offset"] and build_info["memory_romfs_address"] > 0:
            base_address = build_info["memory_romfs_address"]

        position = build_info["romfs_offset"] - ((base_address - address) - 0x08)

        if build_info["image_type"] == IMAGE_TYPE.BOX or build_info["image_type"] == IMAGE_TYPE.COMPRESSED_BOOTROM or build_info["image_type"] == IMAGE_TYPE.ORIG_CLASSIC_BOX or build_info["image_type"] == IMAGE_TYPE.ORIG_CLASSIC_BOOTROM:
            position -= 0x08

        return position & 0xffffffff

    def romfs_base(f, build_info, file_size = 0xffffffff):
        if build_info["image_type"] == IMAGE_TYPE.BOX or build_info["image_type"] == IMAGE_TYPE.COMPRESSED_BOOTROM:
            f.seek(build_info["romfs_offset"] - 0x38)
            build_info["romfs_address"] = (build_meta.read32bit(f) + 0x78)
        elif build_info["image_type"] == IMAGE_TYPE.VIEWER or build_info["image_type"] == IMAGE_TYPE.DREAMCAST:
            f.seek(build_info["romfs_offset"] - 0x30)
            start_offset = build_meta.read32bit(f) + 0x78

            f.seek(build_info["romfs_offset"] - 0x30)
            test_start_offset = build_meta.read32bit(f, "little") + 0x78

            if test_start_offset == (file_size + 0x98):
                start_offset = test_start_offset
                build_info["image_type"] = IMAGE_TYPE.DREAMCAST

            build_info["romfs_address"] = start_offset
        elif build_info["image_type"] == IMAGE_TYPE.COMPRESSED_BOX:
            build_info["romfs_address"] = 0x00
        else:
            build_info["romfs_address"] = -1
        
        return build_info

    def test_romfs(f, base, file_size = 0xffffffff, start_offset = 0):
        base += start_offset

        SIGNATURE_TESTS = [
            {
                "image_type": IMAGE_TYPE.VIEWER, 
                "offset": -0x20,
                "signature": b'\x00\x00\x00\x00\x7A\x46\x4C\x41\x53\x48'
            },
            {
                "image_type": IMAGE_TYPE.VIEWER,
                "offset": -0x20,
                "signature": b'\x00\x00\x00\x00\x52\x4F\x4D\x00'
            },
            {
                "image_type": IMAGE_TYPE.COMPRESSED_BOX,
                "offset": 0,
                "signature": b'\x10\x00\x00\x00\x00\x00\x00\x00'
            },
            {
                "image_type": IMAGE_TYPE.ORIG_CLASSIC_BOOTROM,
                "offset": 0,
                "signature": b'\x96\x03\x18\x69\x00\x04\x00\x00'
            },
            {
                "image_type": IMAGE_TYPE.ORIG_CLASSIC_BOOTROM, # This is from a built alpha bootrom
                "offset": 0,
                "signature": b'\x10\x00\x01\x16\x00\x00\x00\x00'
            },
            {
                "image_type": IMAGE_TYPE.ORIG_CLASSIC_BOX,
                "offset": 0,
                "signature": b'\x10\x00\x00\x09\x00\x00\x00\x00'
            },
            {
                "image_type": IMAGE_TYPE.ORIG_CLASSIC_BOX,
                "offset": 0,
                "signature": b'\x10\x00\x00\x0E\x00\x00\x00\x00'
            },
            {
                "image_type": IMAGE_TYPE.ORIG_CLASSIC_BOX,
                "offset": 0,
                "signature": b'\x10\x00\x00\x0F\x00\x00\x00\x00'
            },
            {
                "image_type": IMAGE_TYPE.BUILD_BUGGED,
                "offset": 0x04,
                "signature": b'\x00\x20\x20\x20'
            },
            {
                "image_type": IMAGE_TYPE.BOX,
                "offset": -0x24,
                "signature": b'\x52\x4F\x4D\x00\x00\x00\x00\x00\x00\x00\x00\x00'
            },
            {
                "image_type": IMAGE_TYPE.BOX,
                "offset": 0,
                "signature": b'\x10\x00\x00\x12\x00\x00\x00\x00'
            },
            {
                "image_type": IMAGE_TYPE.BOX,
                "offset": 0,
                "signature": b'\x10\x00\x00\x11\x00\x00\x00\x00'
            },
            {
                "image_type": IMAGE_TYPE.VIEWER_SCRAMBLED,
                "offset": -0x20,
                "signature": b'\x00\x00\x00\x00\x52\x4F\x4D\x00'
            },
            {
                "image_type": IMAGE_TYPE.VIEWER_SCRAMBLED,
                "offset": -0x1C,
                "signature": b'\x52\x4F\x4D\x00\x00\x00\x00\x00'
            },
            {
                "image_type": IMAGE_TYPE.ULTIMATETV_BOX,
                "offset": 0x00,
                "signature": b'\x10\x00\x04\x00\x00\x00\x00\x00'
            },
        ]

        for sig_test in SIGNATURE_TESTS:
            if sig_test["offset"] < 0 and abs(base + sig_test["offset"]) < file_size:
                f.seek(base + sig_test["offset"], os.SEEK_END)
            elif sig_test["offset"] < file_size and sig_test["offset"] >= 0:
                f.seek(sig_test["offset"] + start_offset)

            romfs_sig = bytes(f.read(len(sig_test["signature"])))

            if sig_test["image_type"] == IMAGE_TYPE.VIEWER_SCRAMBLED:
                if romfs_cipher.unscramble(romfs_sig) == sig_test["signature"]:
                    return sig_test["image_type"]
            else:
                if romfs_sig == sig_test["signature"]:
                    return sig_test["image_type"]

        return None
        
    def read32bit(f, endian = "big", position = -1, start_offset = 0):
        if position != -1:
            f.seek(start_offset + position)

        return int.from_bytes(bytes(f.read(4)), endian)

    def read16bit(f, endian = "big", position = -1, start_offset = 0):
        if position != -1:
            f.seek(start_offset + position)

        return int.from_bytes(bytes(f.read(2)), endian)

    def read8bit(f, endian = "big", position = -1, start_offset = 0):
        if position != -1:
            f.seek(start_offset + position)

        return int.from_bytes(bytes(f.read(1)), endian)

    def readFixedString(f, size = 1, position = -1, start_offset = 0):
        if position != -1:
            f.seek(start_offset + position)

        str_data = bytes(f.read(size))

        str_len = 1
        try:
            str_len = str_data.index(b'\x00')
        except ValueError:
            str_len = size

        return str(str_data[0:str_len], "ascii", "ignore")

    def readData(f, size = 1, position = -1, start_offset = 0):
        if position != -1:
            f.seek(start_offset + position)

        return bytes(f.read(size))

    def default_build_info(path):
        return {
            "path": path,

            "build_version": -1,

            "build_address": -1,
            "start_offset": 0,
            "end_offset": 0,

            "build_size": -1,
            "code_checksum": -1,
            "code_size": -1,
            "jump_offset": -1,

            "data_address": -1,
            "data_offset": -1,
            "data_size": -1,
            "compressed_data_size": -1,
            "bss_size": -1,
            "build_flags": -1,

            "level1_lzj_version": -1,
            "level1_image_address": -1,
            "level1_image_offset": -1,
            "level1_image_size": -1,

            "bootrom_level1_compression": -1,
            "bootrom_level1_address": -1,
            "bootrom_level1_offset": -1,
            "bootrom_level1_size": -1,

            "image_type": IMAGE_TYPE.UNKNOWN,
            "romfs_address": -1,
            "memory_romfs_address": -1,
            "romfs_offset": -1,
            "romfs_end_address": -1,
            "romfs_end_offset": -1,
            "romfs_size": -1,

            "storage_table_offset": -1,
            "wince_romhdr_address": -1,
            "wince_romhdr_offset": -1,
            "wince_romhdr_dllfirst": -1,
            "wince_romhdr_dlllast": -1,
            "wince_romhdr_physfirst": -1,
            "wince_romhdr_physlast": -1,
            "wince_romhdr_ramstart": -1,
            "wince_romhdr_ramfree": -1,
            "wince_romhdr_ramend": -1,
            "wince_romhdr_kernelflags": -1,
            "wince_romhdr_fsrampercent": -1,
            "wince_romhdr_usmiscflags": -1,
            "wince_romhdr_uscputype": -1,

            "footer_size": 0,
            "footer_offset": -1,
            "footer_address": -1,
            "autodisk_offset": -1,
            "autodisk_address": -1,
       }

    
    def detect(path):
        BUILD_START = b'\x10\x00\x00'
        UTV_START = b'\x10\x00\x04'
        ALPHA_START = b'\x10\x00\x01'
        COMPRESSED_BUILD_START = b'\x10\x00\x00\x00'
        AUTODISK_FILEM_BGN_MAGIC = 0x39592841
        AUTODISK_FILEM_END_MAGIC = 0x11993456
        NOROMFS_MAGIC = 0x4E6F4653 # NoFS
        MIN_FILE_SIZE = 0x1000
        LZSS_START = b'\x10\x00\x00'

        build_info = build_meta.default_build_info(path)

        file_size = 0

        def check_offsets(f, start_offset = 0):
            nonlocal build_info, file_size

            f.seek(start_offset)
            if bytes(f.read(len(COMPRESSED_BUILD_START))) == COMPRESSED_BUILD_START:
                build_info["code_checksum"] = build_meta.read32bit(f, "big", 0x08, build_info["start_offset"])
                build_info["build_size"] = build_meta.read32bit(f, "big", 0x0c, build_info["start_offset"]) << 2
                build_info["code_size"] = build_meta.read32bit(f, "big", 0x10, build_info["start_offset"]) << 2

                build_info["build_version"] = build_meta.read32bit(f, "big", 0x14, build_info["start_offset"])

                build_info["build_address"] = build_meta.read32bit(f, "big", 0x30, build_info["start_offset"])

                build_info["end_offset"] = 0
                build_info["level1_image_offset"] = 0x200
                build_info["level1_image_address"] = build_info["build_address"] + build_info["level1_image_offset"]
                build_info["level1_image_size"] = build_meta.read32bit(f, "big", 0x2c, build_info["start_offset"])
                build_info["level1_lzj_version"] = build_meta.read32bit(f, "big", 0x28, build_info["start_offset"])

                build_info["build_flags"] = build_meta.read32bit(f, "big", 0x34, build_info["start_offset"])

                build_info["data_address"] = build_meta.read32bit(f, "big", 0x18, build_info["start_offset"])
                build_info["data_offset"] = build_info["data_address"] - build_info["build_address"]
                build_info["data_size"] = build_meta.read32bit(f, "big", 0x1c, build_info["start_offset"]) << 2
                build_info["bss_size"] = build_meta.read32bit(f, "big", 0x20, build_info["start_offset"]) << 2
                build_info["compressed_data_size"] = build_meta.read32bit(f, "big", 0x38, build_info["start_offset"])

                return True
            else:
                f.seek(start_offset)
                start = bytes(f.read(len(BUILD_START)))
                if start == BUILD_START or start == UTV_START or start == ALPHA_START:
                    build_info["start_offset"] = start_offset

                    build_info["code_checksum"] = build_meta.read32bit(f, "big", 0x08, build_info["start_offset"])
                    build_info["build_size"] = build_meta.read32bit(f, "big", 0x0c, build_info["start_offset"]) << 2
                    build_info["code_size"] = build_meta.read32bit(f, "big", 0x10, build_info["start_offset"]) << 2
                    build_info["jump_offset"] = (build_meta.read16bit(f, "big", 0x02, build_info["start_offset"]) << 2) + 0x04

                    build_info["build_version"] = build_meta.read32bit(f, "big", 0x14, build_info["start_offset"])

                    _romfs_address = build_meta.read32bit(f, "big", 0x24, build_info["start_offset"])

                    if build_info["jump_offset"] > 0x30:
                        build_info["build_address"] = build_meta.read32bit(f, "big", 0x30, build_info["start_offset"])
                        build_info["build_flags"] = build_meta.read32bit(f, "big", 0x34, build_info["start_offset"])
                        build_info["compressed_data_size"] = build_meta.read32bit(f, "big", 0x38, build_info["start_offset"])

                        _compressed_bootrom_level1_address = build_meta.read32bit(f, "big", 0x3c, build_info["start_offset"])
                        if _compressed_bootrom_level1_address > 0 and _compressed_bootrom_level1_address > build_info["build_address"]:
                            _bootrom_level1_offset = (_compressed_bootrom_level1_address - build_info["build_address"])
                            _romfs_offset = file_size

                            if _bootrom_level1_offset <= file_size:
                                build_info["bootrom_level1_address"] = _compressed_bootrom_level1_address
                                build_info["bootrom_level1_offset"] = _bootrom_level1_offset
                    else:
                        # The original classic build's don't specify a build address. So assuming the default.
                        build_info["build_flags"] = 0x00
                        if _romfs_address == 0x9fe00000:
                            build_info["build_address"] = 0x9fc00000 # Classic BootROM
                        else:
                            build_info["build_address"] = 0x9f000000 # Classic AppROM

                    build_info["data_address"] = build_meta.read32bit(f, "big", 0x18, build_info["start_offset"])
                    build_info["data_offset"] = build_info["data_address"] - build_info["build_address"]
                    build_info["data_size"] = build_meta.read32bit(f, "big", 0x1c, build_info["start_offset"]) << 2
                    build_info["bss_size"] = build_meta.read32bit(f, "big", 0x20, build_info["start_offset"]) << 2

                    _romfs_offset = (_romfs_address - build_info["build_address"])

                    if _romfs_offset > file_size:
                        raise Exception("ROMFS is beyond the size of this file! Is this file truncated?")
                    elif _romfs_address != NOROMFS_MAGIC:
                        build_info["romfs_offset"] = _romfs_offset
                        build_info["romfs_address"] = _romfs_address

                        _end_offset = build_info["romfs_offset"]

                        if file_size >= _romfs_offset + 4:
                            build_info["footer_size"] = file_size - _romfs_offset
                            build_info["footer_offset"] = _romfs_offset
                            build_info["footer_address"] = _romfs_address

                            autodisk_metadata_begin_magic = build_meta.read32bit(f, "big", _romfs_offset, build_info["start_offset"])
                            if autodisk_metadata_begin_magic == AUTODISK_FILEM_BGN_MAGIC:
                                autodisk_metadata_size = build_meta.read32bit(f, "big", _romfs_offset + 0x10, build_info["start_offset"])
                                autodisk_file_count = build_meta.read32bit(f, "big", _romfs_offset + 0x14, build_info["start_offset"])

                                if autodisk_metadata_size > 0 and autodisk_metadata_size <= 0x10000 and autodisk_file_count > 0 and autodisk_file_count <= 0x400:
                                    autodisk_filedata_offset = _romfs_offset + autodisk_metadata_size

                                    autodisk_metadata_end_magic = build_meta.read32bit(f, "big", autodisk_filedata_offset - 4, build_info["start_offset"])

                                    if autodisk_metadata_end_magic == AUTODISK_FILEM_END_MAGIC:
                                        build_info["autodisk_offset"] = _romfs_offset
                                        build_info["autodisk_address"] = _romfs_address

                                        _end_offset = file_size

                        build_info["end_offset"] = -1 * (file_size - _end_offset)


                    return True

        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()

            build_info["start_offset"] = 0

            if file_size > MIN_FILE_SIZE:
                if not check_offsets(f, 0) and check_offsets(f, 0x20):
                    build_info["start_offset"] = 0x20

                detected_image_type = build_meta.test_romfs(f, build_info["end_offset"], file_size, 0x00)
                if detected_image_type is None:
                    build_info["start_offset"] = 0
                    build_info["end_offset"] = 0
                    detected_image_type = build_meta.test_romfs(f, build_info["end_offset"], file_size, 0x00)

                if detected_image_type is not None:
                    build_info["image_type"] = detected_image_type

                    if detected_image_type == IMAGE_TYPE.ORIG_CLASSIC_BOX and build_info["build_address"] == 0x9fc00000:
                        detected_image_type = IMAGE_TYPE.ORIG_CLASSIC_BOOTROM

                    if detected_image_type == IMAGE_TYPE.BOX or detected_image_type == IMAGE_TYPE.ORIG_CLASSIC_BOX or detected_image_type == IMAGE_TYPE.ORIG_CLASSIC_BOOTROM:
                        build_info["romfs_size"] = build_meta.read32bit(f, "big", build_info["romfs_offset"] - 0x08, build_info["start_offset"]) << 2
                    else:
                        build_info["romfs_offset"] = file_size
                        build_info["romfs_size"] = build_info["romfs_offset"]

                    build_info["romfs_end_address"] = build_info["romfs_address"] - 8 - (build_info["romfs_size"] * 4)
                    build_info["romfs_end_offset"] = build_info["romfs_offset"] - 8 - (build_info["romfs_size"] * 4)

                    build_info["romfs_offset"] += build_info["start_offset"]
                    build_info["romfs_end_offset"] += build_info["start_offset"]

                    if build_info["bootrom_level1_offset"] >= 0:
                        build_info["image_type"] = IMAGE_TYPE.COMPRESSED_BOOTROM

                        build_info["bootrom_level1_size"] = 0x1c0000 # TODO: Guessed? Do better here.
                        build_info["bootrom_level1_offset"] += build_info["start_offset"]

                        f.seek(build_info["bootrom_level1_offset"] + 0x10)
                        data = f.read(4)

                        if data[1:4] == LZSS_START:
                            build_info["bootrom_level1_compression"] = FILE_COMPRESSION.LZSS
                        else:
                            build_info["bootrom_level1_compression"] = FILE_COMPRESSION.LZJV1

                    if build_info["autodisk_offset"] >= 0:
                        build_info["autodisk_offset"] += build_info["start_offset"]

                    if build_info["romfs_address"] == -1:
                        build_info = build_meta.romfs_base(f, build_info, file_size)

            if build_info["romfs_offset"] != -1 and build_info["romfs_offset"] <= file_size:
                # This is useful for bootrom images.
                build_info["memory_romfs_address"] = build_meta.read32bit(f, "big", (build_info["romfs_offset"] - 0x78)) + 0xB0

            if detected_image_type == IMAGE_TYPE.ULTIMATETV_BOX:
                build_info["storage_table_offset"] = build_info["build_size"]

                build_info["wince_romhdr_address"] = build_meta.read32bit(f, "big", 0x1044, build_info["start_offset"])
                build_info["wince_romhdr_offset"] =  (build_info["wince_romhdr_address"] - build_info["build_address"])
                build_info["wince_romhdr_dllfirst"] = build_meta.read32bit(f, "big", build_info["wince_romhdr_offset"] + 0x00, build_info["start_offset"])
                build_info["wince_romhdr_dlllast"] = build_meta.read32bit(f, "big", build_info["wince_romhdr_offset"] + 0x04, build_info["start_offset"])
                build_info["wince_romhdr_physfirst"] = build_meta.read32bit(f, "big", build_info["wince_romhdr_offset"] + 0x08, build_info["start_offset"])
                build_info["wince_romhdr_physlast"] = build_meta.read32bit(f, "big", build_info["wince_romhdr_offset"] + 0x0c, build_info["start_offset"])
                build_info["wince_romhdr_ramstart"] = build_meta.read32bit(f, "big", build_info["wince_romhdr_offset"] + 0x14, build_info["start_offset"])
                build_info["wince_romhdr_ramfree"] = build_meta.read32bit(f, "big", build_info["wince_romhdr_offset"] + 0x18, build_info["start_offset"])
                build_info["wince_romhdr_ramend"] = build_meta.read32bit(f, "big", build_info["wince_romhdr_offset"] + 0x1c, build_info["start_offset"])
                build_info["wince_romhdr_kernelflags"] = build_meta.read32bit(f, "big", build_info["wince_romhdr_offset"] + 0x34, build_info["start_offset"])
                build_info["wince_romhdr_fsrampercent"] = build_meta.read32bit(f, "big", build_info["wince_romhdr_offset"] + 0x38, build_info["start_offset"])
                build_info["wince_romhdr_uscputype"] = build_meta.read32bit(f, "big", build_info["wince_romhdr_offset"] + 0x40, build_info["start_offset"])
                build_info["wince_romhdr_usmiscflags"] = build_meta.read32bit(f, "big", build_info["wince_romhdr_offset"] + 0x44, build_info["start_offset"])

            f.close()


        return build_info

class build_matryoshka():
    def expand_bootrom_level1(build_info):
        td, tmp_path = tempfile.mkstemp()

        if build_info["bootrom_level1_offset"] > 0:
            with os.fdopen(td, "wb") as t:
                with open(build_info["path"], "rb") as f:
                    f.seek(0, os.SEEK_END)
                    file_size = f.tell()

                    f.seek(build_info["bootrom_level1_offset"] + 0x10)
                    data = f.read(file_size - (build_info["bootrom_level1_offset"] + 0x10))

                    if build_info["bootrom_level1_compression"] == FILE_COMPRESSION.LZSS:
                        d = lzss()
                        t.write(d.Lzss_Expand(data, build_info["bootrom_level1_size"]))
                    else:
                        d = lzj(LZJ_VERSION.VERSION1)
                        t.write(d.Lzj_Expand(data))

                    f.close()
                t.close()

            new_build_info = build_meta.detect(tmp_path)

            new_build_info["is_level1_image"] = True
            new_build_info["original_path"] = build_info["path"]

            return new_build_info
        else:
            return build_info

    def expand_level1(build_info):
        td, tmp_path = tempfile.mkstemp()

        with os.fdopen(td, "wb") as t:
            with open(build_info["path"], "rb") as f:
                f.seek(0, os.SEEK_END)
                file_size = f.tell()

                f.seek(build_info["level1_image_offset"])
                data = f.read(build_info["level1_image_size"])

                d = lzj(LZJ_VERSION(build_info["level1_lzj_version"]))
                t.write(d.Lzj_Expand(data))

                f.close()
            t.close()

            new_build_info = build_meta.detect(tmp_path)

            new_build_info["is_level1_image"] = True
            new_build_info["original_path"] = build_info["path"]

            return new_build_info

class romfs_cipher():
    SCRAMBLE_KEY =b'\xFE\x0F\x8A\x50\x40\x38\x8A\x7C\x14\x22\x84\x7C\xBF\x52\xA4\x50'

    def unscramble(data):
        return tea.decrypt(data, romfs_cipher.SCRAMBLE_KEY)

    def scramble(data):
        return tea.encrypt(data, romfs_cipher.SCRAMBLE_KEY)

    def write_vwr_file(build_info, data, silent = False):
        td, tmp_path = tempfile.mkstemp()

        if not silent:
            print("\tScrambling ROMFS file...")

        file_size = len(data)
        with open(build_info["out_path"], "wb") as f:
            current_position = 0
            while (file_size - current_position) > 8:
                f.write(romfs_cipher.scramble(data[current_position:(current_position + 8)]))

                current_position += 8

                if not silent:
                    print("\r\t\t" + str(int((current_position / file_size) * 100)) + "%", end='', flush=True)

            f.write(data[current_position:(current_position + 8)])
            f.close()

        if not silent:
            print("\r\tDone scrambling ROMFS file!", flush=True)

        if not silent:
            print("\tWrote ROMFS to '" + build_info["out_path"] + "'")

    def unscramble_vwr_file(build_info, silent = False):
        td, tmp_path = tempfile.mkstemp()

        if not silent:
            print("\tUnscrambling vwr file...")

        with os.fdopen(td, "wb") as t:
            with open(build_info["path"], "rb") as f:
                f.seek(0, os.SEEK_END)
                file_size = f.tell()

                current_position = 0
                while (file_size - current_position) > 8:
                    f.seek(current_position)

                    t.write(romfs_cipher.unscramble(f.read(8)))

                    current_position += 8

                    if not silent:
                        print("\r\t\t" + str(int((current_position / file_size) * 100)) + "%", end='', flush=True)

                f.seek(current_position)
                t.write(f.read(8))

                f.close()
            t.close()

        if not silent:
            print("\tDone unscrambling vwr file!", flush=True)

        new_build_info = build_meta.detect(tmp_path)

        new_build_info["is_level1_image"] = True
        new_build_info["original_path"] = build_info["path"]

        return new_build_info
