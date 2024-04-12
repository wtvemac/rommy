import os
from os import listdir
from os.path import isfile
import struct
import re
import json
import ctypes
import io
import tempfile
from lib.lzpf import *
from lib.lzss import *
from lib.build_meta import *
from lib.autodisk import *

class romfs_implode():
    def build_romfs(directory_paths, build_info, build_level = "level0", final_level1_path = None, level1_lzj_version = None, data_blob = b'', autodisk_blob = b'', silent = False, descriptor_table = None, disable_romfs_build = False, disable_romfs_compression = False):
        object_count = 0
        files_blob_size = 0
        romfs_blob = b''
        files_blob_offset = 0
        object_table_offset = 0
        file_list = {}
        romfs_nodes = []

        if not silent and not disable_romfs_build:
            print("\tBuilding romfs")

        endian = ""
        if build_info["image_type"] == IMAGE_TYPE.DREAMCAST:
            endian = "<"
        else:
            endian = ">"

        box_build = False
        if build_info["image_type"] == IMAGE_TYPE.BOX or build_info["image_type"] == IMAGE_TYPE.COMPRESSED_BOX or build_info["image_type"] == IMAGE_TYPE.COMPRESSED_BOOTROM or build_info["image_type"] == IMAGE_TYPE.ORIG_CLASSIC_BOX:
            box_build = True
        else:
            box_build = False

        def _build_romfs(romfs_nodes, parent_address = 0):
            nonlocal endian, romfs_blob, files_blob_offset, object_table_offset, silent

            if romfs_nodes == None or len(romfs_nodes) == 0:
                return 0

            starting_table_offset = object_table_offset - 0x38
            previous_table_offset = -1

            if parent_address > 0:
                parent_address = build_meta.romfs_address(build_info, parent_address)

            for romfs_node in romfs_nodes:
                object_table_offset -= 0x38
                current_table_offset = object_table_offset
                child_list_offset = 0
                data_offset = 0

                if romfs_node["type"] == OBJECT_TYPE.DIRECTORY:
                    data_offset = 0

                    _child_list_offset = _build_romfs(romfs_node["children"], object_table_offset)

                    if _child_list_offset != 0:
                        child_list_offset = build_meta.romfs_address(build_info, _child_list_offset)
                else:
                    child_list_offset = 0
                    _data_offset = files_blob_offset - romfs_node["aligned_size"]

                    romfs_blob[_data_offset:files_blob_offset] = romfs_node["data"]
                    files_blob_offset -= romfs_node["aligned_size"]
                    
                    data_offset = build_meta.romfs_address(build_info, _data_offset)

                if previous_table_offset >= 0:
                    struct.pack_into(
                        endian + "I",
                        romfs_blob,
                        previous_table_offset,
                        build_meta.romfs_address(build_info, current_table_offset)
                    )

                size_param = romfs_node["data_size"]
                compression = "UNKNOWN"
                if romfs_node["compression_type"] == FILE_COMPRESSION.LZPF:
                    size_param |= 0x80000000
                    compression = "LZPF"
                elif romfs_node["compression_type"] == FILE_COMPRESSION.LZSS:
                    size_param |= 0x90000000
                    compression = "LZSS"
                else:
                    compression = "NONE"

                if not silent:
                    print("\tPack[" + compression + "]: " + romfs_node["path"])

                struct.pack_into(
                    endian + "IIIIIII28s",
                    romfs_blob,
                    current_table_offset,
                    romfs_node["next_link"],
                    parent_address,
                    child_list_offset,
                    data_offset,
                    size_param,
                    0,
                    romfs_node["data_checksum"],
                    bytes(romfs_node["name"], "ascii", "ignore")
                )

                previous_table_offset = current_table_offset

            return starting_table_offset

        def _walk_directory(directory_path = "", path = "", depth = 0):
            nonlocal file_list

            search_dir = directory_path + "/" + path

            objects = listdir(search_dir)

            file_objects = []
            for name in objects:
                if depth == 0 and name == "dt.json":
                    continue

                file_path = search_dir + "/" + name
                romfs_path = path + "/" + name

                if isfile(file_path):
                    if romfs_path in file_list:
                        continue
                    else:
                        file_objects.append(romfs_path)

                        file_list[romfs_path] = {
                            "name": name,
                            "file_path": file_path,
                            "type": OBJECT_TYPE.FILE,
                            "children": []
                        }
                else:
                    children = _walk_directory(directory_path, romfs_path, (depth + 1))

                    if romfs_path in file_list:
                        file_list[romfs_path]["children"] += children
                    else:
                        file_objects.append(romfs_path)

                        file_list[romfs_path] = {
                            "name": name,
                            "file_path": file_path,
                            "type": OBJECT_TYPE.DIRECTORY,
                            "children": children
                        }

            if depth == 0:
                if "/" in file_list:
                    file_list["/"]["children"] += file_objects
                else:
                    file_list["/"] = {
                        "name": "",
                        "file_path": "/",
                        "type": OBJECT_TYPE.DIRECTORY,
                        "children": file_objects
                    }
                
            return file_objects


        def _walk_romfs(romfs_paths, depth = 0):
            nonlocal build_info, build_level, descriptor_table, object_count, files_blob_size, box_build, disable_romfs_compression, silent

            _romfs_nodes = []
            for romfs_path in romfs_paths:
                file_path = file_list[romfs_path]["file_path"]

                file_type = file_list[romfs_path]["type"]
                children = []
                compression_type = FILE_COMPRESSION.NONE
                compressed_size = -1
                data = b''
                file_size = 0
                data_size = 0
                aligned_size = 0
                data_checksum = 0
                next_link = 0

                if file_type == OBJECT_TYPE.FILE:
                    data = build_meta.get_file_data(file_path)

                    if len(data) == 0:
                        continue

                    file_size = len(data)

                    romfs_objects = {}
                    dont_compress_list = []
                    compressed_extension_dict = {}
                    compressed_extension_list = []

                    # Force the box build flag
                    if "box_build" in build_info and build_info["box_build"]:
                        box_build = True

                    if box_build and file_size > 0x0a:
                        #object-table-value
                        #object-table-value-then-best
                        #object-table-value-then-extension-list
                        #object-table-value-then-extension-list-then-best
                        #extension-list
                        #extension-list-then-best
                        if not disable_romfs_compression or (descriptor_table != None and "bypass_disable_romfs_compression" in descriptor_table):
                            compression_strategy = "object-table-value-then-best"
                            if descriptor_table != None:
                                dt_build_info = {}
                                if build_level + "_build_info" in descriptor_table:
                                    dt_build_info = descriptor_table[build_level + "_build_info"]

                                if "compression_strategy" in dt_build_info:
                                    compression_strategy = dt_build_info["compression_strategy"]
                                elif "compression_strategy" in descriptor_table:
                                    compression_strategy = descriptor_table["compression_strategy"]
                                else:
                                    compression_strategy = "object-table-value-then-best"

                                if "dont_compress_list" in dt_build_info and hasattr(dt_build_info["dont_compress_list"], "__len__"):
                                    dont_compress_list = dt_build_info["dont_compress_list"]
                                elif "dont_compress_list" in descriptor_table and hasattr(descriptor_table["dont_compress_list"], "__len__"):
                                    dont_compress_list = descriptor_table["dont_compress_list"]

                                if "compressed_extensions" in dt_build_info:
                                    if isinstance(dt_build_info["compressed_extensions"], dict):
                                        compressed_extension_dict = dt_build_info["compressed_extensions"]
                                    elif hasattr(dt_build_info["compressed_extensions"], "__len__"):
                                        compressed_extension_list = dt_build_info["compressed_extensions"]
                                elif "compressed_extensions" in descriptor_table:
                                    if isinstance(descriptor_table["compressed_extensions"], dict):
                                        compressed_extension_dict = descriptor_table["compressed_extensions"]
                                    elif hasattr(descriptor_table["compressed_extensions"], "__len__"):
                                        compressed_extension_list = descriptor_table["compressed_extensions"]

                                if "dont_compress" in dt_build_info:
                                    compression_strategy = "off"
                                elif "dont_compress" in descriptor_table:
                                    compression_strategy = "off"

                                if build_level + "_romfs_objects" in descriptor_table:
                                    romfs_objects = descriptor_table[build_level + "_romfs_objects"]


                            if compression_strategy == "object-table-value" or compression_strategy == "object-table-value-then-best" or compression_strategy == "object-table-value-then-extension-list" or compression_strategy == "object-table-value-then-extension-list-then-best":
                                if romfs_path in romfs_objects and "compression_type" in romfs_objects[romfs_path]:
                                    compression_type = FILE_COMPRESSION(romfs_objects[romfs_path]["compression_type"])
                                elif compression_strategy == "object-table-value-then-best":
                                    compression_strategy = "best"
                                elif compression_strategy == "object-table-value-then-extension-list":
                                    compression_strategy = "extension-list"
                                elif compression_strategy == "object-table-value-then-extension-list-then-best":
                                    compression_strategy = "extension-list-then-best"

                            if compression_strategy == "extension-list" or compression_strategy == "extension-list-then-best":
                                extension = os.path.splitext(file_path)[1][1:].lower()

                                if extension in compressed_extension_dict:
                                    compression_type = FILE_COMPRESSION(compressed_extension_dict[extension])
                                elif compression_strategy == "extension-list-then-best" or extension in compressed_extension_list:
                                    compression_strategy = "best"

                            if compression_strategy == "off" or romfs_path in dont_compress_list:
                                compression_type = FILE_COMPRESSION.NONE
                            elif compression_strategy == "best":
                                lzpf_len = file_size + 1
                                lzpf_data = b''
                                lzss_len = file_size + 1
                                lzss_data = b''

                                try:
                                    c = lzpf()
                                    lzpf_data = c.Lzpf_Compress(data)
                                    lzpf_len = len(lzpf_data)
                                except:
                                    pass

                                try:
                                    c = lzss()
                                    lzss_data = c.Lzss_Compress(data)
                                    lzss_len = len(lzss_data)
                                except:
                                    pass

                                if lzss_len > file_size and lzpf_len > file_size:
                                    compression_type = FILE_COMPRESSION.NONE
                                elif lzss_len >= lzpf_len:
                                    compression_type = FILE_COMPRESSION.LZPF
                                    data = lzpf_data
                                else:
                                    compression_type = FILE_COMPRESSION.LZSS
                                    data = lzss_data
                            elif compression_type == FILE_COMPRESSION.LZPF:
                                c = lzpf()
                                data = c.Lzpf_Compress(data)
                            elif compression_type == FILE_COMPRESSION.LZSS:
                                c = lzss()
                                data = c.Lzss_Compress(data)
                            else:
                                compression_type = FILE_COMPRESSION.NONE

                        if compression_type != FILE_COMPRESSION.NONE:
                            _file_size = bytearray(4)
                            struct.pack_into(
                                endian + "I",
                                _file_size,
                                0,
                                file_size
                            )

                            compressed_size = data_size
                            data = _file_size + data
                        else:
                            compressed_size = -1

                    data_size = len(data)
                    alignment_size = 4 - (data_size % 4)
                    for a in range(4 - (data_size % 4)):
                        data.append(0)

                    aligned_size = len(data)

                    data_checksum = build_meta.chunked_checksum(data, 1)
                else: 
                    if descriptor_table != None and "object" in descriptor_table:
                        if depth == 0 and romfs_path in descriptor_table["object"] and "next_link" in descriptor_table["object"][romfs_path]:
                            next_link = descriptor_table["object"][romfs_path]["next_link"]

                    children = _walk_romfs(build_meta.natural_sort(file_list[romfs_path]["children"]), (depth + 1))

                object_count += 1
                files_blob_size += aligned_size

                if not silent:
                    print("\r\t\tObject count: " + str(object_count), end='', flush=True)
                    
                romfs_node = {
                    "address": 0,
                    "position": 0,
                    "type": file_type,
                    "next_link": next_link,
                    "parent": 0,
                    "child_list": 0,
                    "data_address": 0,
                    "reserve": 0,
                    "data_checksum": data_checksum,
                    "compression_type": compression_type,
                    "compressed_size": compressed_size,
                    "data_offset": 0,
                    "file_size": file_size,
                    "data_size": data_size,
                    "aligned_size": aligned_size,
                    "data": data,
                    "name": file_list[romfs_path]["name"],
                    "file_path": file_path,
                    "path": romfs_path,
                    "depth": depth,
                    "children": children
                }

                _romfs_nodes.append(romfs_node)

            return _romfs_nodes

        if not disable_romfs_build:
            if not silent:
                if len(directory_paths) == 1:
                    print("\tWalking directory:", directory_paths[0])
                else:
                    print("\tWalking directories:", ", ".join(directory_paths))


            for directory_path in directory_paths:
                _walk_directory(directory_path)

            if "/" in file_list:
                romfs_nodes = _walk_romfs(build_meta.natural_sort(file_list["/"]["children"]))

            if not silent:
                print("\r\tDone.                                 ", flush=True)

            romfs_size = files_blob_size + (0x38 * object_count)

            files_blob_offset = files_blob_size
            object_table_offset = romfs_size
            extra_alloc_bytes = 0

            build_info["romfs_offset"] = object_table_offset

            if build_info["image_type"] == IMAGE_TYPE.DREAMCAST:
                build_info["romfs_address"] = object_table_offset + 0x98
            elif box_build:
                extra_alloc_bytes = 8
            elif build_info["romfs_address"] <= 0 or build_info["romfs_address"] == 0xffffffff:
                build_info["romfs_address"] = 0x80800000
            else:
                if romfs_size > build_info["romfs_address"]:
                    build_info["romfs_address"] = romfs_size + 0x98

            romfs_blob = bytearray(romfs_size + extra_alloc_bytes)
            _build_romfs(romfs_nodes)

            if not silent:
                print("\tDone building ROMFS.")

        if box_build:
            if not silent:
                print("\tRebulding ROM file.")

            level1_build_blob = b''

            if final_level1_path != None and os.path.isfile(final_level1_path):
                level1_build_blob = bytearray(open(final_level1_path, "rb").read())

                # Checksumming this build just in case it was edited and the checksum wasn't fixed!
                if len(level1_build_blob) > 0x14:
                    code_size = int.from_bytes(bytes(level1_build_blob[0x10:0x14]), "big") << 2
                    if len(level1_build_blob) >= code_size:
                        level1_build_blob[0x08:0x0c] = bytearray(0x04)
                        code_checksum = build_meta.chunked_checksum(level1_build_blob[0x00:code_size])
                        struct.pack_into(
                            endian + "I",
                            level1_build_blob,
                            0x08,
                            code_checksum
                        )


            if romfs_blob == None or len(romfs_blob) == 0 and "source_build_path" in build_info and "romfs_offset" in build_info and "romfs_size" in build_info and build_info["romfs_size"] > 0 and build_info["romfs_offset"] > 0 and build_info["image_type"] != IMAGE_TYPE.COMPRESSED_BOX:
                romfs_blob = build_meta.get_file_data(build_info["source_build_path"], (build_info["romfs_offset"] - build_info["romfs_size"]), build_info["romfs_size"])
                
            return build_meta.build_blob(build_info, endian, romfs_blob, data_blob, autodisk_blob, level1_build_blob, level1_lzj_version, silent)
        else:
            return romfs_blob

    def pack(origin, romfs_folders, source_build_path = None, out_path = None, image_type = None, final_level1_path = None, level1_lzj_version = None, data_blob = b'', autodisk_blob = b'', silent = False, build_info = None, build_level = "level0", use_descriptor_file = True, disable_romfs_build = False, disable_romfs_compression = False):
        if build_info == None and source_build_path != None:
            build_info = build_meta.detect(source_build_path)

        descriptor_table_path = origin + "/dt.json"
        descriptor_table = None
        if use_descriptor_file and os.path.isfile(descriptor_table_path):
            descriptor_table = json.loads(build_meta.get_file_data(descriptor_table_path).decode())

        if build_info == None:
            build_info = build_meta.default_build_info(out_path)

        if image_type != None:
            build_info["image_type"] = image_type
        elif "image_type" in build_info:
            build_info["image_type"] = IMAGE_TYPE(build_info["image_type"])

        if source_build_path != None:
            build_info["source_build_path"] = source_build_path
        elif "path" in build_info:
            build_info["source_build_path"] = build_info["path"]

        if out_path != None:
            build_info["out_path"] = out_path
        elif "path" in build_info:
            build_info["out_path"] = build_info["path"]
        elif "source_build_path" in build_info:
            build_info["out_path"] = build_info["source_build_path"]

        if not silent:
            build_meta.print_build_info(build_info, build_level.capitalize() + " Type: ")

        if build_info["image_type"] == IMAGE_TYPE.COMPRESSED_BOX or len(romfs_folders) == 0:
            disable_romfs_build = True

        if build_info["image_type"] == IMAGE_TYPE.VIEWER_SCRAMBLED:
            romfs_cipher.write_vwr_file(build_info, romfs_implode.build_romfs(romfs_folders, build_info, build_level, final_level1_path, level1_lzj_version, data_blob, autodisk_blob, silent, descriptor_table, disable_romfs_build, disable_romfs_compression), silent)
        elif build_info["image_type"] == IMAGE_TYPE.BOX or build_info["image_type"] == IMAGE_TYPE.COMPRESSED_BOOTROM or build_info["image_type"] == IMAGE_TYPE.ORIG_CLASSIC_BOX:
            build_meta.write_object_file(build_info, romfs_implode.build_romfs(romfs_folders, build_info, build_level, final_level1_path, level1_lzj_version, data_blob, autodisk_blob, silent, descriptor_table, disable_romfs_build, disable_romfs_compression), silent)
        else:
            build_meta.write_object_file(build_info, romfs_implode.build_romfs(romfs_folders, build_info, build_level, final_level1_path, level1_lzj_version, data_blob, autodisk_blob, silent, descriptor_table, disable_romfs_build, disable_romfs_compression), silent)
