import os
import sys
import struct
import math
import tempfile
import shutil
import zlib
import json
from lib.lzpf import *
from lib.lzss import *
from lib.build_meta import *
from lib.autodisk import *
import shutil

class romfs_explode():
    def read_node(f, build_info, address, read_data = True):
        position = build_meta.romfs_position(build_info, address)

        f.seek(position)

        file_info = [0, 0, 0, 0, 0, 0, ""]

        try:
            if build_info["image_type"] == IMAGE_TYPE.DREAMCAST:
                file_info = struct.unpack_from("<IIIIIII28s", bytes(f.read(0x38)))
            else:
                file_info = struct.unpack_from(">IIIIIII28s", bytes(f.read(0x38)))
        except:
            print("WARNING: stopping. Can't read address @" + hex(address) + " (resolves to position " + hex(position) + " in the file)")
            return None

        file_type = OBJECT_TYPE.UNKNOWN
        if file_info[3] == 0 and file_info[4] == 0 and file_info[6] == 0:
            file_type = OBJECT_TYPE.DIRECTORY
        else: 
            file_type = OBJECT_TYPE.FILE

        name_len = 1
        try:
            name_len = file_info[7].index(b'\x00')
        except ValueError:
            name_len = 28

        name = str(file_info[7][0:name_len], "ascii", "ignore")

        data = b''
        datap1 = b''

        file_position = build_meta.romfs_position(build_info, file_info[3])

        data_size = file_info[4]
        compression_type = FILE_COMPRESSION.UNKNOWN
        compressed_size = -1

        if read_data and file_type == OBJECT_TYPE.FILE and file_info[3] > 0 and file_info[4] > 0 and file_position > 0:
            f.seek(file_position)

            if build_meta.is_box_build(build_info["image_type"]) and (data_size & 0xF0000000) != 0:
                size_param = data_size
                compressed_size = data_size - (data_size & 0xFF000000)

                data = bytes(f.read(compressed_size))
                datap1 = bytes(f.read(1))
                
                data_size = int.from_bytes(bytes(data[0:4]), "big")

                compressed_size -= 4

                if (size_param & 0x90000000) == 0x90000000:
                    compression_type = FILE_COMPRESSION.LZSS

                    d = lzss()
                    data = d.Lzss_Expand(data[4:], data_size)

                    data_size = len(data)
                elif (size_param & 0x80000000) == 0x80000000:
                    compression_type = FILE_COMPRESSION.LZPF

                    d = lzpf()
                    data = d.Lzpf_Expand(data[4:])

                    data_size = len(data)
            else:
                data_size -= (data_size & 0xFF000000)

                compression_type = FILE_COMPRESSION.NONE
                compressed_size = -1
                data = bytes(f.read(data_size))
                datap1 = bytes(f.read(1))
        elif not read_data:
            if build_meta.is_box_build(build_info["image_type"]) and (data_size & 0xF0000000) != 0:
                size_param = data_size
                compressed_size = data_size - (data_size & 0xFF000000)
                data_size = compressed_size

                if (size_param & 0x90000000) == 0x90000000:
                    compression_type = FILE_COMPRESSION.LZSS
                elif (size_param & 0x80000000) == 0x80000000:
                    compression_type = FILE_COMPRESSION.LZPF
                else:
                    compression_type = FILE_COMPRESSION.NONE


        return {
            "address": address,
            "address_calculated": (build_info["memory_romfs_address"] - (build_info["romfs_offset"] - build_meta.romfs_position(build_info, address))),
            "position": position,
            "type": file_type,
            "next_link": file_info[0],
            "parent": file_info[1],
            "parent_calculated": (build_info["memory_romfs_address"] - (build_info["romfs_offset"] - build_meta.romfs_position(build_info, file_info[1]))),
            "child_list": file_info[2],
            "data_address": file_info[3],
            "data_offset": file_position,
            "reserve": file_info[5],
            "data_checksum": file_info[6],
            "compression_type": compression_type,
            "compressed_size": compressed_size,
            "data_size": data_size,
            "datap1": datap1, # The box wants the byte after the date to be 0x00. Rommy doesn't care but this is used for a warning about that.
            "data": data,
            "name": name,
            "children": []
        }

    def walk_romfs(f, build_info, address, parent_address, parent_calculated, is_base = False, read_data = True):
        items = []

        while address != 0:
            file_info = romfs_explode.read_node(f, build_info, address, read_data)

            if file_info == None:
                break

            if (file_info["parent"] == parent_address) or (file_info["parent_calculated"] == parent_calculated):
                items.append(file_info)

                if file_info["child_list"] != 0:
                    file_info["children"] = romfs_explode.walk_romfs(f, build_info, file_info["child_list"], address, file_info["address_calculated"], False, read_data)

            if is_base:
                address = 0
            else:
                address = file_info["next_link"]

        return items

    def extract_selected_romfs(build_info, silent = False, read_data = True):
        allowable_level1_types = [
            IMAGE_TYPE.VIEWER_SCRAMBLED,
            IMAGE_TYPE.COMPRESSED_BOX,
            IMAGE_TYPE.COMPRESSED_BOOTROM,
        ]

        allowable_types = [
            IMAGE_TYPE.VIEWER,
            IMAGE_TYPE.BOX,
            IMAGE_TYPE.ORIG_CLASSIC_BOX,
            IMAGE_TYPE.ORIG_CLASSIC_BOOTROM,
            IMAGE_TYPE.COMPRESSED_BOOTROM,
            IMAGE_TYPE.DREAMCAST
        ]

        if build_info["image_type"] in allowable_types:
            return romfs_explode.get_nodes(build_info, read_data)
        else:
            if not silent:
                if build_info["image_type"] in allowable_level1_types:
                    print("\tNot in a format that can be dumped. Beep boop. Attempting to correct...")
                else:
                    print("\tNot in a supported format that can be dumped.")
                    
            return None


    def process_romfs(build_info, silent = False, read_data = True, level1_file = None):
        allowable_level1_types = [
            IMAGE_TYPE.VIEWER_SCRAMBLED,
            IMAGE_TYPE.COMPRESSED_BOX,
            IMAGE_TYPE.COMPRESSED_BOOTROM,
        ]

        if build_info["image_type"] == IMAGE_TYPE.BUILD_BUGGED:
            raise Exception("!! Bugged approm file.  Please re-run parts through the new decompressTool!")

            return None

        if level1_file != None:
            if build_info["image_type"] in allowable_level1_types:
                secondart_build_info = None
                if not silent:
                    print("\nAttemping level1 image (peeling back onion)")

                if build_info["image_type"] == IMAGE_TYPE.VIEWER_SCRAMBLED:
                    secondart_build_info = romfs_cipher.unscramble_vwr_file(build_info, silent)
                    if not silent:
                        build_meta.print_build_info(secondart_build_info, "\nUnscrambled Type: ")

                if build_info["image_type"] == IMAGE_TYPE.COMPRESSED_BOOTROM:
                    if not silent:
                        print("Expanding bootrom level1. This could take a while...")
                    secondart_build_info = build_matryoshka.expand_bootrom_level1(build_info)
                    if not silent:
                        print("Done!")
                        build_meta.print_build_info(secondart_build_info, "\nLevel1 Type: ")
                elif build_info["image_type"] == IMAGE_TYPE.COMPRESSED_BOX:
                    if not silent:
                        print("Expanding build. This could take a while...")
                    secondart_build_info = build_matryoshka.expand_level1(build_info)
                    if not silent:
                        print("Done!")
                        build_meta.print_build_info(secondart_build_info, "\nLevel1 Type: ")

                if secondart_build_info != None:
                    if level1_file != "!tmp" and "is_level1_image" in secondart_build_info.keys() and secondart_build_info["is_level1_image"]:
                        shutil.copyfile(secondart_build_info["path"], level1_file)
                        os.remove(secondart_build_info["path"])
                        secondart_build_info["path"] = level1_file

                    return romfs_explode.extract_selected_romfs(secondart_build_info, silent, read_data), secondart_build_info
            elif build_info["image_type"] == IMAGE_TYPE.UNKNOWN:
                if not silent:
                    print("Nothing I can do...")

            return None, None
        else:
            return romfs_explode.extract_selected_romfs(build_info, silent, read_data), build_info


    def get_nodes(build_info, read_data = True):
        romfs_nodes = []

        with open(build_info["path"], "rb") as f:
            address = (build_info["romfs_address"] - (0x38 + 0x08))

            romfs_nodes = romfs_explode.walk_romfs(f, build_info, address, 0x00000000, 0x00000000, True, read_data)
            f.close()

        return romfs_nodes

    def walk_nodes(level, romfs_nodes, build_info, callback, path = "", depth = 0):
        if callback != None:
            idx = 0
            for _romfs_nodes in romfs_nodes:
                node_path = path + "/" + _romfs_nodes["name"]

                romfs_node = {
                    "depth_index": idx,
                    "type": _romfs_nodes["type"],
                    "name": _romfs_nodes["name"],
                    "next_link": _romfs_nodes["next_link"],
                    "table_address": _romfs_nodes["address"],
                    "table_offset": _romfs_nodes["position"],
                    "data_address": _romfs_nodes["data_address"],
                    "data_offset": _romfs_nodes["data_offset"],
                    "size": _romfs_nodes["data_size"],
                    "compressed_size": _romfs_nodes["compressed_size"],
                    "data": _romfs_nodes["data"],
                    "datap1": _romfs_nodes["datap1"],
                    "compression_type": _romfs_nodes["compression_type"],
                    "path": node_path,
                    "depth": depth
                }

                idx += 1

                callback(level, romfs_node, build_info)

                if len(_romfs_nodes["children"]) > 0:
                    romfs_explode.walk_nodes(level, _romfs_nodes["children"], build_info, callback, node_path, depth + 1)
    
    def walk(origin, callback, silent = False, read_data = True, level1_file = ""):
        build_info = build_meta.detect(origin)

        if not silent:
            build_meta.print_build_info(build_info)

        romfs_nodes, _ = romfs_explode.process_romfs(build_info, silent, read_data, None)
        if romfs_nodes != None:
            romfs_explode.walk_nodes("level0", romfs_nodes, build_info, callback)

        if level1_file != None:
            romfs_nodes, level1_build_info = romfs_explode.process_romfs(build_info, silent, read_data, level1_file)
            if romfs_nodes != None:
                romfs_explode.walk_nodes("level1", romfs_nodes, level1_build_info, callback)

    def list(origin, simplify_sizes = False, level1_file = None):
        last_offset = 0

        current_level = ""

        def _list(level, romfs_node, build_info):
            nonlocal last_offset, current_level

            if current_level != level:
                if current_level != "":
                    print("")

                print("LEGEND{ FILE_NAME TABLE_OFFSET DATA_OFFSET (FILE_SIZE); OFFSET=ABSOLUTE_OFFSET|RELATIVE_OFFSET }\n")

                print("-- Files for '" + level + "':\n")
                current_level = level

            data_offset_display = ""
            table_offset_display = ""

            if romfs_node["table_address"] == romfs_node["table_offset"]:
                table_offset_display = hex(romfs_node["table_offset"]) + " "
            else:
                table_offset_display = hex(romfs_node["table_address"]) + "|" + hex(romfs_node["table_offset"]) + " "

            if romfs_node["type"] == OBJECT_TYPE.DIRECTORY:
                print(("\t" * romfs_node["depth"]) + (romfs_node["name"] + "/") + "\t" + table_offset_display)
            else:
                compressed = False
                data_size = romfs_node["size"]
                if romfs_node["compressed_size"] > 0:
                    compressed = True
                    data_size = romfs_node["compressed_size"]

                size = "0B"
                if simplify_sizes:
                    size = build_meta.simplify_size(data_size)
                else:
                    size = str(data_size) + "B"

                if romfs_node["data_address"] == romfs_node["data_offset"]:
                    data_offset_display = hex(romfs_node["data_offset"]) + " "
                else:
                    data_offset_display = hex(romfs_node["data_address"]) + "|" + hex(romfs_node["data_offset"]) + " "

                print(("\t" * romfs_node["depth"]) + romfs_node["name"].ljust(20) + "\t" + table_offset_display + "\t" + data_offset_display + "\t(" + size + (":compressed=" + str(romfs_node["compression_type"]) if (compressed) else "") + ")")
                last_offset = romfs_node["table_offset"]

        if level1_file == None:
            level1_file = "!tmp"

        romfs_explode.walk(origin, _list, True, False, level1_file)

    def unpack(origin, destination = "./out", silent = False, level1_file = "", create_descriptor_file = True, disable_data_dump = False):
        if not os.path.isdir(destination):
            os.makedirs(destination, 0o777, True)

            if not os.path.isdir(destination):
                raise Exception("Destination doesn't exist")

        shutil.copy(origin, destination + "/template.bin")

        # compression_strategy:
        #   object-table-value-then-best: use compression_type value in object table, otherwise best (DEFAULT)
        #   object-table-value: use compression_type value in object table, otherwise none
        #   best: try none, lzpf and lzss on all files and choose best.
        #   extension-list: use matched extension in compressed_extensions dictionary ({"txt": XXX, "gif": XXX}), otherwise none
        #   off: don't compress anything
        #
        # You can use  "dont_compress" array to block compression from a list of ROMFS file paths

        descriptor_table = {
            "origin": origin,
            "level0_build_info": {},
            "level0_romfs_objects": {},
            "level1_file": level1_file,
            "level1_build_info": {},
            "level1_romfs_objects": {},
            "destination": destination,
            "template_file": "template.bin",
            "compression_strategy": "object-table-value-then-best"
        }

        def _unpack(level, romfs_node, build_info):
            if romfs_node["depth"] == 0 and romfs_node["depth_index"] == 0:
                print("\tLEGEND{ Unpack[COMPRESSION]: TABLE_OFFSET DATA_OFFSET FILE_PATH; OFFSET=ABSOLUTE_OFFSET|RELATIVE_OFFSET }")

            path = destination + "/" + level + "-romfs/" + romfs_node["path"]

            descriptor_table[level + "_build_info"] = build_info

            if not disable_data_dump:
                descriptor_table[level + "_romfs_objects"][romfs_node["path"]] = {
                    "type": romfs_node["type"],
                    "name": romfs_node["name"],
                    "offset": romfs_node["table_offset"],
                    "next_link": romfs_node["next_link"],
                    "size": romfs_node["size"],
                    "compression_type": romfs_node["compression_type"],
                    "depth": romfs_node["depth"]
                }

                compression = "UNKNOWN"
                if romfs_node["compression_type"] == FILE_COMPRESSION.LZPF:
                    compression = "LZPF"
                elif romfs_node["compression_type"] == FILE_COMPRESSION.LZSS:
                    compression = "LZSS"
                else:
                    compression = "NONE"

                data_offset_display = ""
                table_offset_display = ""

                if romfs_node["table_address"] == romfs_node["table_offset"]:
                    table_offset_display = hex(romfs_node["table_offset"]) + " "
                else:
                    table_offset_display = hex(romfs_node["table_address"]) + "|" + hex(romfs_node["table_offset"]) + " "

                warning = ""
                if romfs_node["type"] != OBJECT_TYPE.DIRECTORY:
                    if romfs_node["data_address"] == romfs_node["data_offset"]:
                        data_offset_display = hex(romfs_node["data_offset"]) + " "
                    else:
                        data_offset_display = hex(romfs_node["data_address"]) + "|" + hex(romfs_node["data_offset"]) + " "

                    if "datap1" in romfs_node and romfs_node["datap1"] != b'\x00':
                        warning = "(data+1 not 0x00)"

                if not silent:
                    print("\tUnpack[" + compression + "]: " + table_offset_display + data_offset_display + romfs_node["path"], warning)

                if romfs_node["type"] == OBJECT_TYPE.DIRECTORY:
                    if not os.path.isdir(path):
                        os.makedirs(path, 0o777, True)
                else:
                    with open(path, "wb") as f:
                        f.write(romfs_node["data"])
                        f.close()

        if level1_file:
            level1_file = destination + "/" + level1_file

        romfs_explode.walk(origin, _unpack, silent, not disable_data_dump, level1_file)

        if create_descriptor_file:
            with open(destination + "/dt.json", "w") as f:
                f.write(json.dumps(descriptor_table, sort_keys=True, indent=4))
                f.close()
