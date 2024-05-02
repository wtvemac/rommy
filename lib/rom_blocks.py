import os
from os import listdir
import re
import random
from enum import Enum
from lib.lzss import *
import zlib
from lib.build_meta import *

"""
    All integers are big endian.
    
    Ver 1 and 2 header:

    Bytes 0x00-0x04   [utin32]: ROM Upgrade Block Magic [always 0x96031889]
    Bytes 0x04-0x08   [utin32]: Compressed data length
    Bytes 0x08-0x0c   [utin32]: Uncompressed data length
    Bytes 0x0c-0x10   [utin32]: Uncompressed data CRC32
    Bytes 0x10-0x11    [utin8]: Compression type [0=none, 1=lzss, 2=lzh, 6=zlib/deflate]
    Bytes 0x11-0x12    [utin8]: ??? unknown1 [always 0x01]
    Bytes 0x12-0x14   [utin16]: ??? unknown2 [always 0xffff]
    Bytes 0x14-0x18   [utin32]: Data offset or address (in full build)
    Bytes 0x18-0x1a   [utin16]: Build block header version (upgrade version) [1=original for classic or 2=older classic and everything else]
    Bytes 0x1a-0x1c   [utin16]: Compressed data offset
    Bytes 0x1c-0x1e   [utin16]: Block index
    Bytes 0x1e-0x20   [utin16]: Block flags
    Bytes 0x20-0x24   [utin32]: Total block data size
    Bytes 0x24-0x44[str[0x20]]: -- MESSAGE --

    Ver 2 header continues:

    Bytes 0x44-0x48[0x04]: Previous block data size
    Bytes 0x48-0x4a[0x02]: Signature data length
    Bytes 0x4a-0x4c[0x02]: Signature data offset
    Bytes 0x4c-0x4e[0x02]: Signature data kind [1=test, 2=prod and 3=diag]
    Bytes 0x4e-0x50[0x02]: ??? unknown3 [always 0xffff]
"""

class BLOCK_COMPRESSION_TYPE(int, Enum):
    NONE = 0x00
    LZSS = 0x01
    LZH  = 0x02
    DEFLATE = 0x06
    BSTR = 0xfe # Best, allowing block size to scale
    BEST = 0xff # Best for the current block size

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

class BLOCK_SIGNATURE_TYPE(int, Enum):
    NONE = 0x00
    TEST = 0x01
    PROD = 0x02
    DIAG = 0x03

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

class BLOCK_HEADER_VERSION(int, Enum):
    VER1 = 0x01
    VER2 = 0x02

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

class rom_blocks():
    def write_object_file(out_path, data, silent = False):
        with open(out_path, 'wb') as f:
            f.write(data)

            f.close()

        if not silent:
            print("\tWrote ROM to '" + out_path + "'")

    def default_block_info(path):
        return {
            "path": path,
            "name": os.path.basename(path),

            "upgrade_block_header_version": -1,

            "block_index": -1,
            "previous_block_data_size": -1,
            "total_block_data_size": -1,
            "upgrade_block_message": -1,

            "block_flags": -1,
            "rom_address": -1,

            "uncompressed_data_size": -1,
            "uncompressed_data_crc32": -1,
            "calculated_uncompressed_data_crc32": -1,
            "uncompressed_data": bytearray(0),

            "compression_type": -1,
            "compressed_data_offset": -1,
            "compressed_data_size": -1,
            "compressed_data": bytearray(0),

            "signature_data_type": -1,
            "signature_data_offset": -1,
            "signature_data_size": -1,
           "signature_data": bytearray(0),

            "unknown1": 1,
            "unknown2": 0xffff,
            "unknown3": 0xffff,
       }
    
    def find_rom_parts(search_dir, read_data = True, silent = False, selected_rom_type = "", selected_build_type = ""):
        blocks = {
            "bootrom": {},
            "approm": {},
            "approm_block_count": 0,
            "bootrom_block_count": 0,
            "block_count": 0
        }

        objects = build_meta.natural_sort(listdir(search_dir))

        file_objects = []
        for name in objects:
            build_type = ""
            rom_type = ""

            if matches := re.search(r"^([a-zA-Z0-9\-\_]*?)(-part|part|)[0-9]+.rom$", name, re.IGNORECASE):
                build_type = "approm"
                rom_type = matches.group(1)
            elif matches := re.search(r"^([a-zA-Z0-9\-\_]*?)(-part|part|)[0-9]+.brom$", name, re.IGNORECASE):
                build_type = "bootrom"
                rom_type = matches.group(1)
            else:
                continue

            block_info = rom_blocks.detect(search_dir + "/" + name, read_data, silent)

            if block_info != None:
                rom_type = matches.group(1)
                if not rom_type:
                    rom_type = "build"

                rom_type = rom_type.upper()

                if not rom_type in blocks[build_type]:
                    blocks[build_type][rom_type] = []

                if (selected_build_type == "" or selected_build_type == build_type) and (selected_rom_type == "" or selected_rom_type == rom_type):
                    blocks[build_type][rom_type].append(block_info)

                    blocks[build_type + "_block_count"] += 1
                    blocks["block_count"] += 1

        return blocks

    def select_block_list(blocks):
        build_type = ""
        rom_type = ""

        if blocks["approm_block_count"] > 0:
            build_type = "approm"
            rom_type = list(blocks["approm"].keys())[0]
        elif blocks["bootrom_block_count"] > 0:
            build_type = "bootrom"
            rom_type = list(blocks["bootrom"].keys())[0]

        return build_type, rom_type

    def count_rom_parts(search_dir, selected_rom_type = "", selected_build_type = ""):
        blocks = rom_blocks.find_rom_parts(search_dir, False, True, selected_rom_type, selected_build_type)

        return blocks["block_count"]

    def detect(path, read_data = True, silent = False):
        ROM_BLOCK_MAGIC = 0x96031889

        block_info = rom_blocks.default_block_info(path)

        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()

            rom_block_magic = build_meta.read32bit(f, "big", 0x00)

            if rom_block_magic == ROM_BLOCK_MAGIC:
                block_info["upgrade_block_header_version"] = BLOCK_HEADER_VERSION(build_meta.read16bit(f, "big", 0x18))

                block_info["block_index"] = build_meta.read16bit(f, "big", 0x1c)
                block_info["upgrade_block_message"] = build_meta.readFixedString(f, 0x20, 0x24)
                block_info["total_block_data_size"] = build_meta.read32bit(f, "big", 0x20)

                block_info["block_flags"] = build_meta.read16bit(f, "big", 0x1e)
                block_info["rom_address"] = build_meta.read32bit(f, "big", 0x14)

                block_info["uncompressed_data_size"] = build_meta.read32bit(f, "big", 0x08)
                block_info["uncompressed_data_crc32"] = build_meta.read32bit(f, "big", 0x0c)

                block_info["compression_type"] = BLOCK_COMPRESSION_TYPE(build_meta.read8bit(f, "big", 0x10))
                block_info["compressed_data_offset"] = build_meta.read16bit(f, "big", 0x1a)
                block_info["compressed_data_size"] = build_meta.read32bit(f, "big", 0x04)

                if read_data and block_info["compressed_data_size"] > 0 and block_info["compressed_data_offset"] > 0 and file_size >= (block_info["compressed_data_offset"] + block_info["compressed_data_size"]):
                    block_info["compressed_data"] = build_meta.readData(f, block_info["compressed_data_size"], block_info["compressed_data_offset"])

                    if block_info["compression_type"] == BLOCK_COMPRESSION_TYPE.LZSS:
                        block_info["uncompressed_data"] = lzss().Lzss_Expand(block_info["compressed_data"])
                    elif block_info["compression_type"] == BLOCK_COMPRESSION_TYPE.DEFLATE:
                        block_info["uncompressed_data"] = zlib.decompress(block_info["compressed_data"])
                    else:
                        block_info["uncompressed_data"] = block_info["compressed_data"]

                    block_info["calculated_uncompressed_data_crc32"] = build_meta.crc32(block_info["uncompressed_data"])

                if block_info["upgrade_block_header_version"] > BLOCK_HEADER_VERSION.VER1:
                    block_info["signature_data_type"] = BLOCK_SIGNATURE_TYPE(build_meta.read16bit(f, "big", 0x4c))
                    block_info["signature_data_offset"] = build_meta.read16bit(f, "big", 0x4a)
                    block_info["signature_data_size"] = build_meta.read16bit(f, "big", 0x48)

                    block_info["unknown1"] = build_meta.read8bit(f, "big", 0x11)

                    block_info["previous_block_data_size"] = build_meta.read32bit(f, "big", 0x44)

                    if read_data and block_info["signature_data_size"] > 0 and block_info["signature_data_offset"] > 0 and file_size >= (block_info["signature_data_offset"] + block_info["signature_data_size"]):
                        block_info["signature_data"] = build_meta.readData(f, block_info["signature_data_size"], block_info["signature_data_offset"])
            else:
                #raise Exception("Bad ROM upgrade block. Magic doesn't match. " + path)
                if not silent:
                    print("\tBad ROM upgrade block. Magic doesn't match. " + path)

                return None

        return block_info

    def sign_data(signature_type, data):
        signature_size = 0xC5

        signature_data = b'eMac' * max((math.ceil(signature_size >> 2) + 1), 1)
        signature_data = signature_data[0:signature_size]

        return signature_data

    def default_message(block_index, total_blocks, is_last_block = False, last_message = ""):
        # Start the bipolar goodness!

        regular_messages = [
            "Data {recv_data_size} of {total_data_size}",
            "Block {index} of {total}",
            "Don't stop believin'",
            "We haven't failed.. yet",
            "So... How's the weather",
            "Don't let the past ruin the now",
            "Every mistake adds to your story",
            "Make each day your masterpiece",
            "JUST.. DO IT! {recv_data_size} of {total_data_size}",
            "..I.. FU ..I.. FU ..I..",
            "I love you. Don't kill me...",
            "Fart a day keeps the butt at bay",
            "The gass pass to pass gas- 12345",
            "Farts are just the ass applaudng",
            "Live, laugh, fart",
            "Wheeeeeeee!",
            "Wheeeeee-OH NO!",
            "Beep boop beep. FATAL. ERROR...",
            "I'm scared... {index} of {total}",
            "Self test error...",
            "I've got a right stinky clunge",
            "My starfish speaks to the toilet",
            "He tht lives on hope.dies fartng",
            "Sacrificing box to the WTV gods",
            "My message chirp is a robot fart",
            "Beep Boop! {recv_data_size} of {total_data_size}",
            "FYI... This build wont work",
            "You smell... {index} of {total}",
        ]

        last_messages = [
            "Man down...",
            "SHIP SHIP SHIP SHIP SHIP",
            "SHIP IT AND BREAK MATT'S BOX",
            "Thank you for flying WebTV Air",
            "Hasta la vista. Baby",
            "Target acquired. Will destroy...",
            "May the force be with you",
            "BOOGIE ON DOWN",
            "THE LIBYANS",
            "FARTING IN 3... 2... 1...",
            "DESTRUCTING IN 3... 2... 1..."
        ]

        if is_last_block:
            message = random.choice(last_messages)
        else:
            message = random.choice(regular_messages)

        if message == last_message:
            return rom_blocks.default_message(block_index, total_blocks, is_last_block, last_message)

        return message

    def list(origin, simplify_sizes = False, selected_rom_type = "", selected_build_type = ""):
        blocks = rom_blocks.find_rom_parts(origin, False, False, selected_rom_type, selected_build_type)

        def _list(build_type):
            print(build_type.capitalize() + " Upgrade Blocks")

            for rom_type in blocks[build_type]:
                indent = "\t"
                if rom_type != "BUILD" and rom_type != "WTV":
                    print("\t" + rom_type)
                    indent = "\t\t"

                for rom_block in blocks[build_type][rom_type]:
                    print(indent + rom_block["name"])

                    infos = []
                    
                    if rom_block["block_index"] >= 0:
                        infos.append("Index: " + hex(rom_block["block_index"]))

                    if rom_block["rom_address"] >= 0:
                        infos.append("Location: " + hex(rom_block["rom_address"]))

                    if rom_block["block_flags"] >= 0:
                        infos.append("Flags: " + hex(rom_block["block_flags"]))

                    if rom_block["signature_data_type"] >= 0:
                        signature_type = "UNKNOWN"
                        if rom_block["signature_data_type"] == BLOCK_SIGNATURE_TYPE.TEST:
                            signature_type = "TEST"
                        elif rom_block["signature_data_type"] == BLOCK_SIGNATURE_TYPE.PROD:
                            signature_type = "PROD"
                        elif rom_block["signature_data_type"] == BLOCK_SIGNATURE_TYPE.DIAG:
                            signature_type = "DIAG"

                        infos.append("Signature type: " + signature_type)

                    if rom_block["compression_type"] >= 0:
                        compression = "UNKNOWN"
                        if rom_block["compression_type"] == BLOCK_COMPRESSION_TYPE.LZSS:
                            compression = "LZSS"
                        elif rom_block["compression_type"] == BLOCK_COMPRESSION_TYPE.LZH:
                            compression = "LZH"
                        elif rom_block["compression_type"] == BLOCK_COMPRESSION_TYPE.DEFLATE:
                            compression = "DEFLATE"

                        infos.append("Compression type: " + compression)

                    if rom_block["compressed_data_size"] >= 0:
                        size = "0B"
                        if simplify_sizes:
                            size = build_meta.simplify_size(rom_block["compressed_data_size"])
                        else:
                            size = str(rom_block["compressed_data_size"]) + "B"

                        infos.append("Compressed size: " + size)

                    if rom_block["uncompressed_data_size"] >= 0:
                        size = "0B"
                        if simplify_sizes:
                            size = build_meta.simplify_size(rom_block["uncompressed_data_size"])
                        else:
                            size = str(rom_block["uncompressed_data_size"]) + "B"

                        infos.append("Uncompressed size: " + size)

                    print(indent + "\t" + ", ".join(infos))

                    if len(rom_block["upgrade_block_message"]) > 0:
                        print(indent + "\t\tMessage: " + rom_block["upgrade_block_message"])

        if blocks["block_count"] > 0:
            if blocks["approm_block_count"] > 0:
                _list("approm")

            if blocks["bootrom_block_count"] > 0:
                _list("bootrom")
        else:
            print("\tNo upgrade blocks found")

    def unpack(origin, destination = "./out", silent = False, block_file_extension = ".rom", block_size = 0x10000, address_base = 0x00000000, header_version = BLOCK_HEADER_VERSION.VER2, compression_type = BLOCK_COMPRESSION_TYPE.BSTR, signature_type = BLOCK_SIGNATURE_TYPE.PROD, message_templates = []):
        ROM_BLOCK_MAGIC = 0x96031889
        check_rom_blocks = []
        write_rom_blocks = []

        flags = 0x0000
        current_block_data_size = 0x00

        if not silent:
            print("\tBuilding ROM blocks. This could take a while.")

        with open(origin, "rb") as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()

            check_rom_blocks.append({
                "offset": 0x00,
                "size": min(file_size, block_size),
                "compression_type": compression_type,
                "signature_type": signature_type,
                "block_data": bytearray(0x00)
            })

            if file_size > block_size:
                last_block_offset = max((file_size - block_size), block_size)
                last_block_size = (file_size - last_block_offset)

                check_rom_blocks.append({
                    "offset": last_block_offset,
                    "size": last_block_size,
                    "compression_type": compression_type,
                    "signature_type": signature_type,
                    "block_data": bytearray(0x00)
                })

                for block_offset in range(block_size, last_block_offset, block_size):
                    block_size = min(block_size, (last_block_offset - block_offset))

                    check_rom_blocks.append({
                        "offset": block_offset,
                        "size": block_size,
                        "compression_type": compression_type,
                        "signature_type": signature_type,
                        "block_data": bytearray(0x00)
                    })

            write_block_index = 0x00
            check_block_index = 0x00
            last_check_part_index = len(check_rom_blocks)
            while check_block_index < last_check_part_index:
                rom_block = check_rom_blocks[check_block_index]

                f.seek(rom_block["offset"])

                data_address = address_base + rom_block["offset"]

                header_data = bytearray(0x00)
                signature_data = bytearray(0x00)
                compressed_data = bytearray(0x00)
                uncompressed_data = bytearray(f.read(rom_block["size"]))

                rom_block["name"] = "part" + ("%03d" % write_block_index) + block_file_extension

                if rom_block["compression_type"] == BLOCK_COMPRESSION_TYPE.BSTR:
                    zlib_compressed_data1 = zlib.compress(uncompressed_data, 9)

                    uncompressed_data2 = bytearray(0x00)
                    zlib_compressed_data2 = bytearray(0x00)
                    if (check_block_index + 1) < last_check_part_index:
                        uncompressed_data2 = uncompressed_data + f.read(check_rom_blocks[(check_block_index + 1)]["size"])
                        zlib_compressed_data2 = zlib.compress(uncompressed_data2, 9)

                    uncompressed_data3 = bytearray(0x00)
                    zlib_compressed_data3 = bytearray(0x00)
                    if (check_block_index + 2) < last_check_part_index:
                        uncompressed_data3 = uncompressed_data2 + f.read(check_rom_blocks[(check_block_index + 2)]["size"])
                        zlib_compressed_data3 = zlib.compress(uncompressed_data3, 9)

                    ratio1 = (len(zlib_compressed_data1) / len(uncompressed_data))
                    ratio2 = (len(zlib_compressed_data2) / len(uncompressed_data2)) if len(uncompressed_data2) > 0 else 0xff
                    ratio3 = (len(zlib_compressed_data3) / len(uncompressed_data3)) if len(uncompressed_data3) > 0 else 0xff

                    best_ratio = min(ratio1, ratio2, ratio3)

                    if best_ratio >= 1:
                        rom_block["compression_type"] = BLOCK_COMPRESSION_TYPE.NONE
                        compressed_data = uncompressed_data
                    elif best_ratio == ratio1:
                        rom_block["compression_type"] = BLOCK_COMPRESSION_TYPE.DEFLATE
                        compressed_data = zlib_compressed_data1
                    elif best_ratio == ratio2:
                        rom_block["compression_type"] = BLOCK_COMPRESSION_TYPE.DEFLATE
                        uncompressed_data = uncompressed_data2
                        compressed_data = zlib_compressed_data2
                        check_block_index += 1
                    elif best_ratio == ratio3:
                        rom_block["compression_type"] = BLOCK_COMPRESSION_TYPE.DEFLATE
                        uncompressed_data = uncompressed_data3
                        compressed_data = zlib_compressed_data3
                        check_block_index += 2

                elif rom_block["compression_type"] == BLOCK_COMPRESSION_TYPE.BEST:
                    zlib_compressed_data = zlib.compress(uncompressed_data, 9)

                    if (len(zlib_compressed_data) + 4) > len(uncompressed_data):
                        rom_block["compression_type"] = BLOCK_COMPRESSION_TYPE.NONE
                        compressed_data = uncompressed_data
                    else:
                        rom_block["compression_type"] = BLOCK_COMPRESSION_TYPE.DEFLATE
                        compressed_data = zlib_compressed_data

                elif rom_block["compression_type"] == BLOCK_COMPRESSION_TYPE.LZSS:
                    compressed_data = lzss().Lzss_Compress(uncompressed_data)
                elif rom_block["compression_type"] == BLOCK_COMPRESSION_TYPE.DEFLATE:
                    compressed_data = zlib.compress(uncompressed_data, 9)
                else:
                    rom_block["compression_type"] = BLOCK_COMPRESSION_TYPE.NONE

                    compressed_data = uncompressed_data

                # Add tail that zlib doesn't add in the way WebTV wants (2 byte header with 8 byte tail)
                if rom_block["compression_type"] == BLOCK_COMPRESSION_TYPE.DEFLATE:
                    tail_data = bytearray(0x08)
                    struct.pack_into(
                        "<II",
                        tail_data,
                        0,
                        zlib.crc32(uncompressed_data),
                        len(uncompressed_data)
                    )

                    compressed_data += tail_data

                if header_version == BLOCK_HEADER_VERSION.VER2:
                    signature_data = rom_blocks.sign_data(signature_type, uncompressed_data)

                    header_data = bytearray(0x50)
                    struct.pack_into(
                        ">IIIIBBHIHHHHI32sIHHHH",
                        header_data,
                        0,
                        ROM_BLOCK_MAGIC,
                        len(compressed_data),
                        len(uncompressed_data),
                        build_meta.crc32(uncompressed_data),
                        rom_block["compression_type"],
                        0x01,
                        0xFFFF,
                        data_address,
                        0x02, # Header version
                        len(header_data) + len(signature_data),
                        write_block_index,
                        flags,
                        0x00, # Total block data size filled in later
                        bytearray(0), # Message, written later
                        current_block_data_size,
                        len(signature_data),
                        len(header_data),
                        rom_block["signature_type"],
                        0xFFFF,
                    )
                else:
                    header_data = bytearray(0x44)
                    struct.pack_into(
                        ">IIIIBBHIHHHHI32s",
                        header_data,
                        0,
                        ROM_BLOCK_MAGIC,
                        len(compressed_data),
                        len(uncompressed_data),
                        build_meta.crc32(uncompressed_data),
                        rom_block["compression_type"],
                        0x01,
                        0xFFFF,
                        data_address,
                        0x01, # Header version
                        len(header_data),
                        write_block_index,
                        flags,
                        0x00, # Total block data size filled in later
                        bytearray(0) # Message, written later
                    )

                rom_block["block_data"] = header_data + signature_data + compressed_data

                current_block_data_size += len(rom_block["block_data"])

                rom_block["current_block_data_size"] = current_block_data_size

                write_rom_blocks.append(rom_block)
                write_block_index += 1
                check_block_index += 1

        total_block_data_size = current_block_data_size

        last_message = ""
        for block_index in range(len(write_rom_blocks)):
            message_text = ""
            if block_index < len(message_templates):
                message_text = message_templates[block_index]
            elif len(message_templates) > 0:
                message_text = message_templates[len(message_templates) - 1]
            else:
                message_text = rom_blocks.default_message(block_index, len(write_rom_blocks), ((block_index + 1) == len(write_rom_blocks)), last_message)

            message_text = message_text.replace("{index}", str(block_index + 1))
            message_text = message_text.replace("{total}", str(len(write_rom_blocks)))
            message_text = message_text.replace("{recv_data_size}", build_meta.simplify_size(write_rom_blocks[block_index]["current_block_data_size"]))
            message_text = message_text.replace("{total_data_size}", build_meta.simplify_size(total_block_data_size))
            message_text = message_text.replace("{current_block_size}", build_meta.simplify_size(len(rom_block["block_data"])))
            message_text = message_text.replace("{name}", rom_block["name"])

            write_rom_blocks[block_index]["message_data"] = bytes(message_text, "ascii", "ignore")

        if not os.path.isdir(destination):
            os.makedirs(destination, 0o777, True)

        for rom_block in write_rom_blocks:
            if not silent:
                compression = "NONE"
                if rom_block["compression_type"] >= 0:
                    if rom_block["compression_type"] == BLOCK_COMPRESSION_TYPE.LZSS:
                        compression = "LZSS"
                    elif rom_block["compression_type"] == BLOCK_COMPRESSION_TYPE.DEFLATE:
                        compression = "DEFLATE"

                print("\tUnpack[" + compression + "]: " + rom_block["name"])

                struct.pack_into(
                    ">I32s",
                    rom_block["block_data"],
                    0x20,
                    total_block_data_size,
                    rom_block["message_data"]
                )
            with open(destination + "/" + rom_block["name"], "wb") as f:
                f.write(rom_block["block_data"])
                f.close()

    def pack(origin, destination = "./out.o", silent = False, selected_rom_type = "", selected_build_type = ""):
        if not silent:
            print("Creating " + destination + "...")

        if not silent:
            print("  Scanning ROM upgrade blocks... This could take a while.")

        blocks = rom_blocks.find_rom_parts(origin, True, silent, selected_rom_type, selected_build_type)

        build_type, rom_type = rom_blocks.select_block_list(blocks)

        if build_type != "" and rom_type != "":
            file_data = bytearray(0)

            display_rom_type = rom_type
            if rom_type != "BUILD" and rom_type != "WTV":
                display_rom_type = rom_type + " "
            else:
                display_rom_type = ""

            if not silent:
                print("  Build " + display_rom_type + build_type.capitalize() + " Image")

            for rom_block in blocks[build_type][rom_type]:
                _data_offset = rom_block["rom_address"]
                data = rom_block["uncompressed_data"]
                data_size = len(data)

                data_offset = _data_offset
                if data_offset >= 0xbfc00000:
                    data_offset -= (data_offset & 0xffe00000)
                elif data_offset >= 0xbf000000:
                    data_offset -= (data_offset & 0xffc00000)
                else:
                    data_offset &= 0xFFFFFFF

                end_length = (data_offset + data_size)

                compression = "NONE"
                if rom_block["compression_type"] >= 0:
                    if rom_block["compression_type"] == BLOCK_COMPRESSION_TYPE.LZSS:
                        compression = "LZSS"
                    elif rom_block["compression_type"] == BLOCK_COMPRESSION_TYPE.DEFLATE:
                        compression = "DEFLATE"

                if not silent:
                    offset_tell = "offset " + hex(data_offset) + "-" + hex(data_offset + data_size)

                    if _data_offset != offset_tell:
                        offset_tell += "; address " + hex(_data_offset) + "-" + hex(_data_offset + data_size)

                    print("\tPack[" + compression + "]: " + rom_block["name"] + " [" + offset_tell + "]")

                    if len(rom_block["upgrade_block_message"]) > 0:
                        print("\t\tMessage: " + rom_block["upgrade_block_message"])

                if data_offset >= len(file_data):
                    file_data = file_data + (b'\x00' * (data_offset - len(file_data))) + data
                else:
                    file_data = file_data[0:data_offset] + data + file_data[(data_offset + data_size):]

            rom_blocks.write_object_file(destination, file_data, silent)
        else:
            raise Exception("Couldn't find any upgrade block files.")
