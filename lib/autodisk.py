import os.path
from os import listdir
from os.path import isfile
import binascii
import struct
import re
from lib.build_meta import *

"""
    All integers are big endian.

    Bytes 0x00-0x04[uint32]: Autodisk File Database Index/Metadata Magic [0x39592841]
    Bytes 0x04-0x08[uint32]: Index/Metadata CRC
    Bytes 0x08-0x0c[uint32]: ??? version?
    Bytes 0x0c-0x10[uint32]: ??? version?
    Bytes 0x10-0x14[uint32]: Size in bytes of the file DB index/metadata section needs to be 0x10000 or less
    Bytes 0x14-0x18[uint32]: Number of files in the DB needs to be 0x400 or less
    Bytes 0x18-XXXx[uint32]: File Index/Metadata
        0x00-0x04[uint32]: ??? version?
        0x04-0x08[uint32]: file size
        0x08-0x0c[uint32]: file data offset
        0x0c-0x10[uint32]: file name offset
        0x10-0x14[uint32]: CRC of file data
    Bytes XXX:XXX+0x04 File names
    Bytes XXX:XXX+0x04 Autodisk File Database Index/Metadata End Magic [0x11993456]

    Bytes XXX+0x04:ZZZ: File Data

    If autodisk version is 0x47726179 (Gray) then no write is made.
    Otherwise it checks the CRC32 of the build version string with what's local.
"""
class autodisk():


    def get_file_data(path):
        data = b''

        with open(path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            data_size = f.tell()

            f.seek(0)
            data = f.read(data_size)

            f.close()

        return bytearray(data)

    def build_image(directory_paths, build_info, silent = False, descriptor_table = None):
        AUTODISK_FILEM_BGN_MAGIC = 0x39592841
        AUTODISK_FILEM_END_MAGIC = 0x11993456
        MAX_METADATA_SIZE = 0x10000
        MAX_FILE_COUNT = 0x400
        AUTODISK_ALIGNMENT = 0x20000
        object_count = 0
        filemeta_top_blob_size = 0
        filemeta_name_blob_size = 0
        filemeta_blob_size = 0
        filedata_blob_size = 0
        autodisk_alignment_size = 0
        autodisk_size = 0
        file_list = {}

        if not silent:
            print("Building autodisk image")

        endian = ""
        if build_info["image_type"] == IMAGE_TYPE.DREAMCAST:
            endian = "<"
        else:
            endian = ">"

        def _walk_directory(directory_path = "", path = "", depth = 0):
            nonlocal file_list

            search_dir = directory_path + "/" + path

            objects = listdir(search_dir)

            file_objects = []
            for name in objects:
                if depth == 0 and name == "dt.json":
                    continue

                file_path = search_dir + "/" + name
                autodisk_path = path + "/" + name

                if isfile(file_path):
                    if autodisk_path in file_list:
                        continue
                    else:
                        file_objects.append(autodisk_path)

                        file_list[autodisk_path] = {
                            "name": name,
                            "file_path": file_path,
                            "type": OBJECT_TYPE.FILE,
                            "children": []
                        }
                else:
                    children = _walk_directory(directory_path, autodisk_path, (depth + 1))

                    if autodisk_path in file_list:
                        file_list[autodisk_path]["children"] += children
                    else:
                        file_objects.append(autodisk_path)

                        file_list[autodisk_path] = {
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

        def _walk_autodisk(autodisk_paths, depth = 0):
            nonlocal descriptor_table, object_count, filemeta_name_blob_size, filedata_blob_size, silent

            _autodisk_nodes = []
            for autodisk_path in autodisk_paths:
                file_path = file_list[autodisk_path]["file_path"]

                file_type = file_list[autodisk_path]["type"]
                data = b''
                filename = b''
                file_size = 0
                aligned_size = 0
                filename_offset = filemeta_name_blob_size
                filedata_offset = filedata_blob_size
                data_crc = 0

                if file_type == OBJECT_TYPE.FILE:
                    filename = bytearray(bytes(autodisk_path, "ascii", "ignore")) + bytearray(b'\x00')
                    data = autodisk.get_file_data(file_path)

                    if len(data) == 0:
                        continue

                    data_crc = build_meta.crc32(data)

                    file_size = len(data)
                    for a in range(build_meta.align(file_size)):
                        data.append(0)

                    object_count += 1
                    filemeta_name_blob_size += len(filename)
                    filedata_blob_size += len(data)

                    if not silent:
                        print("\r\t\tObject count: " + str(object_count), end='', flush=True)

                    autodisk_node = {
                        "unknown_x": 1,
                        "local_path": file_path,
                        "path": autodisk_path,
                        "name": os.path.basename(file_path),
                        "size": file_size,
                        "aligned_size": len(data),
                        "filename_offset": filename_offset,
                        "filedata_offset": filedata_offset,
                        "filename": filename,
                        "data_crc": data_crc,
                        "data": data
                    }
                    _autodisk_nodes.append(autodisk_node)
                else:
                    _autodisk_nodes += _walk_autodisk(reversed(build_meta.natural_sort(file_list[autodisk_path]["children"])), (depth + 1))

            return _autodisk_nodes

        def _build_autodisk(autodisk_nodes):
            nonlocal endian, object_count, filemeta_top_blob_size, filemeta_name_blob_size, filemeta_blob_size, filedata_blob_size, autodisk_alignment_size, autodisk_size, silent, AUTODISK_FILEM_BGN_MAGIC, AUTODISK_FILEM_END_MAGIC

            if autodisk_nodes == None or len(autodisk_nodes) == 0:
                return None

            filemeta_blob = bytearray(filemeta_blob_size)
            filedata_blob = bytearray(0)

            struct.pack_into(
                endian + "IIIIII",
                filemeta_blob,
                0x00,
                AUTODISK_FILEM_BGN_MAGIC,
                0x00, # Metadata CRC, calculated later
                0x01,
                0x01,
                filemeta_blob_size,
                object_count,
            )

            filemeta_top_offset = 0x18
            filemeta_name_offset = filemeta_top_blob_size
            for autodisk_node in autodisk_nodes:
                if not silent:
                    print("\tAutodisk Pack: " + autodisk_node["path"])

                struct.pack_into(
                    endian + "IIIII",
                    filemeta_blob,
                    filemeta_top_offset,
                    autodisk_node["unknown_x"],
                    autodisk_node["size"],
                    autodisk_node["filedata_offset"],
                    autodisk_node["filename_offset"],
                    autodisk_node["data_crc"],
                )

                filename_size = len(autodisk_node["filename"])

                filemeta_blob[filemeta_name_offset:(filemeta_name_offset + filename_size)] = autodisk_node["filename"]

                filemeta_top_offset += 0x14
                filemeta_name_offset += filename_size

                filedata_blob += autodisk_node["data"]

            struct.pack_into(
                endian + "I",
                filemeta_blob,
                (filemeta_blob_size - 0x04),
                AUTODISK_FILEM_END_MAGIC
            )

            metadata_crc = build_meta.crc32(filemeta_blob[0x08:])

            struct.pack_into(
                endian + "I",
                filemeta_blob,
                0x04,
                metadata_crc
            )

            return (filemeta_blob + filedata_blob + bytearray(autodisk_alignment_size))

        if not silent:
            if len(directory_paths) == 1:
                print("\tWalking directory:", directory_paths[0])
            else:
                print("\tWalking directories:", ", ".join(directory_paths))

        for directory_path in directory_paths:
            _walk_directory(directory_path)

        autodisk_nodes = _walk_autodisk(build_meta.natural_sort(file_list["/"]["children"]))

        if not silent:
            print("\r\tDone.                                 ", flush=True)

        if object_count > MAX_FILE_COUNT:
            raise Exception("To many autodisk files. There are '" + len(autodisk_nodes) + "' files but there can only be a max of '" + MAX_FILE_COUNT + "' files!")

        filemeta_top_blob_size = (0x18 + (object_count * 0x14))
        filemeta_blob_size = filemeta_top_blob_size + filemeta_name_blob_size
        filemeta_blob_size += build_meta.align(filemeta_blob_size) + 0x200

        if filemeta_blob_size > MAX_METADATA_SIZE:
            raise Exception("Autodisk metadata is too large. We're at '" + len(filemeta_blob_size) + "' bytes but it maxes out at '" + MAX_METADATA_SIZE + "'! This might be because of super long file path names?")

        autodisk_size = filemeta_blob_size + filedata_blob_size
        autodisk_alignment_size = build_meta.align(autodisk_size, AUTODISK_ALIGNMENT)
        autodisk_size += autodisk_alignment_size

        autodisk_blob = _build_autodisk(autodisk_nodes)

        if not silent:
            print("\tDone building Autodisk.")

        return autodisk_blob

    def is_proper(f, build_info, silent = False):
        AUTODISK_FILEM_BGN_MAGIC = 0x39592841
        AUTODISK_FILEM_END_MAGIC = 0x11993456
        CRC_OFFSET = 8

        metadata_begin_magic = build_meta.read32bit(f, "big", build_info["autodisk_offset"])

        if metadata_begin_magic == AUTODISK_FILEM_BGN_MAGIC:
            metadata_found_crc = build_meta.read32bit(f, "big", build_info["autodisk_offset"] + 0x04)
            metadata_size = build_meta.read32bit(f, "big", build_info["autodisk_offset"] + 0x10)
            build_info["autodisk_file_count"] = build_meta.read32bit(f, "big", build_info["autodisk_offset"] + 0x14)
            
            if metadata_size > 0 and metadata_size <= 0x10000 and build_info["autodisk_file_count"] > 0 and build_info["autodisk_file_count"] <= 0x400:
                build_info["autodisk_filedata_offset"] = build_info["autodisk_offset"] + metadata_size

                metadata_end_magic = build_meta.read32bit(f, "big",  build_info["autodisk_filedata_offset"] - 4)

                if metadata_end_magic == AUTODISK_FILEM_END_MAGIC:
                    metadata_calculated_crc = build_meta.crc32(build_meta.get_data(f, build_info["autodisk_offset"] + 0x08, metadata_size - 0x08))

                    if metadata_calculated_crc != metadata_found_crc:
                        if not silent:
                            print("\tWARNING: the autodisk metadata checksum doesn't match! found=" + hex(metadata_found_crc) + ", calculated=" + hex(metadata_calculated_crc))

                    return True
                else:
                    if not silent:
                        print("\tERROR: bad ROM autodisk metadata block. Magic doesn't match. found=" + hex(metadata_end_magic) + ", expected=" + hex(AUTODISK_FILEM_END_MAGIC))
            else:
                if not silent:
                    print("\tERROR: bad ROM autodisk metadata block. Bad metadata size or file count. size=" + hex(metadata_size) + ", file count=" + hex(build_info["autodisk_file_count"]))
        else:
            if not silent:
                print("\tERROR: bad ROM autodisk metadata block. Header magic doesn't match. found=" + hex(metadata_begin_magic) + ", expected=" + hex(AUTODISK_FILEM_BGN_MAGIC))

        return False

    def walk(origin, callback, silent = False, read_data = True):
        if callback != None:
            build_info = build_meta.detect(origin)

            with open(build_info["path"], "rb") as f:
                if autodisk.is_proper(f, build_info, silent):

                    for i in range(0, build_info["autodisk_file_count"]):
                        f.seek(build_info["autodisk_offset"] + 0x18 + (0x14 * i))
                        file_info = struct.unpack_from(">IIIII", bytes(f.read(0x14)))

                        f.seek(build_info["autodisk_offset"] + 0x18 + (0x14 * build_info["autodisk_file_count"]) + file_info[3])
                        _path = struct.unpack_from(">255s", bytes(f.read(0xFF)))[0]
                        path = str(_path[0:_path.index(b'\x00')], "ascii", "ignore")

                        data = None
                        if read_data:
                            f.seek(build_info["autodisk_filedata_offset"] + file_info[2])
                            data = bytes(f.read(file_info[1]))

                        autodisk_node = {
                            "unknown_x": file_info[0],
                            "size": file_info[1],
                            "filedata_offset": file_info[2],
                            "filename_offset": file_info[3],
                            "data_crc": file_info[4],
                            "data": data,
                            "path": path,
                            "name": os.path.basename(path),
                        }

                        callback(autodisk_node)
                else:
                    if not silent:
                        print("No files found!")

                f.close()

    def list(origin, simplify_sizes = False, read_data = False):
        def _list(autodisk_node):
            size = "0B"
            if simplify_sizes:
                size = build_meta.simplify_size(autodisk_node["size"])
            else:
                size = str(autodisk_node["size"]) + "B"

            print(autodisk_node["path"] + "\t(" + size + ")")

        autodisk.walk(origin, _list)


    def unpack(origin, destination = "./out", silent = False):
        if not os.path.isdir(destination):
            os.mkdir(destination)

            if not os.path.isdir(destination):
                raise Exception("Destination doesn't exist")

        autodisk_objects = {}

        def _unpack(autodisk_node):
            nonlocal silent

            autodisk_objects[autodisk_node["path"]] = {
                "unknown_x": autodisk_node["unknown_x"],
                "size": autodisk_node["size"],
                "filedata_offset": autodisk_node["filedata_offset"],
                "filename_offset": autodisk_node["filename_offset"],
                "data_crc": autodisk_node["data_crc"],
                "path": autodisk_node["path"],
                "name": autodisk_node["name"]
            }

            path = destination + "/" + autodisk_node["path"]

            if not silent:
                print("\tAutodisk Unpack: " + autodisk_node["path"])

            _dir = os.path.dirname(path)
            if not os.path.isdir(_dir):
                os.makedirs(_dir)

            with open(path, "wb") as f:
                f.write(autodisk_node["data"])
                f.close()

        autodisk.walk(origin, _unpack, silent)

        return autodisk_objects
