import os
from os import listdir
import re
import shutil
import json
from subprocess import Popen, PIPE
import ctypes as defcts
from lib.build_meta import *

class utv_tools():
    def resolve_executable_command(command_sections):
        windows_command_prefix = utv_tools.get_windows_command_prefix()

        if windows_command_prefix != "":
            command_sections = [windows_command_prefix] + command_sections

        return command_sections

    def get_wine():
        available_commands = [
            "wine"
        ]

        for available_command in available_commands:
            if shutil.which(available_command) != None:
                return available_command

        return None

    def get_windows_command_prefix():
        if os.name != 'nt':
            wine_cmd = utv_tools.get_wine()

            if wine_cmd == None:
                raise Exception("Couldn't find wine location. Can't use UTV image tools!")
            else:
                return wine_cmd
        else:
            return ""

    def get_perl():
        available_commands = [
            "perl",
            "perl.exe"
        ]

        for available_command in available_commands:
            if shutil.which(available_command) != None:
                return available_command

        return None

    def get_perl_command_prefix():
        perl_command_prefix = utv_tools.get_perl()

        if perl_command_prefix == None:
            raise Exception("Perl needs to be installed. Please install Perl (32 or 64 bit) and make sure it's available in the PATH env.")

        return perl_command_prefix

    def load_cecompress():
        tools_path = os.path.abspath("lib/utv-tools/")

        cdllobj = None

        if os.name != 'nt':
            import zugbruecke.ctypes as winects

            ctypes = winects
        else:
            if sys.maxsize > 2**32:
                raise Exception("In order to deal with UltimateTV's WinCE NK compression, you need to run this in a 32-bit version of Python.")

            ctypes = defcts

        CECompress3DLL = ctypes.cdll.LoadLibrary(tools_path + "/CECompressv3.dll")

        CECompress = CECompress3DLL.CECompress
        CECompress.argtypes = (
            ctypes.POINTER(ctypes.c_char), ctypes.c_uint,
            ctypes.POINTER(ctypes.c_char), ctypes.c_uint,
            ctypes.c_ushort,
            ctypes.c_uint
        )
        CECompress.memsync = [
            {
                "pointer": [0],
                "length": [1],
                "type": ctypes.c_char
            },
            {
                "pointer": [2],
                "length": [3],
                "type": ctypes.c_char
            }
        ]
        CECompress.restype = ctypes.c_uint

        ###

        CEDecompress = CECompress3DLL.CEDecompress
        CEDecompress.argtypes = [
            ctypes.POINTER(ctypes.c_char), ctypes.c_uint,
            ctypes.POINTER(ctypes.c_char), ctypes.c_uint,
            ctypes.c_uint,
            ctypes.c_ushort,
            ctypes.c_uint
        ]
        CEDecompress.memsync = [
            {
                "pointer": [0],
                "length": [1],
                "type": ctypes.c_char
            },
            {
                "pointer": [2],
                "length": [3],
                "type": ctypes.c_char
            }
        ]
        CEDecompress.restype = ctypes.c_uint

        return CECompress, CEDecompress
    
    def walk_compressfs_partition_table(origin, build_info):
        TABLE_MAGIC = 0x74696D6E

        partition_table_info = {
            "table_checksum": -1,
            "partition_count": 0,
            "partitions": []
        }

        if "storage_table_offset" in build_info and build_info["storage_table_offset"] > 0:
            with open(build_info["path"], "rb") as f:
                f.seek(build_info["storage_table_offset"])

                table_header = struct.unpack_from(">III", bytes(f.read(0x0c)))

                magic = table_header[2]

                if magic == TABLE_MAGIC:
                    partition_table_info["table_checksum"] = table_header[0]
                    partition_table_info["partition_count"] = table_header[1]

                    for image_index in range(partition_table_info["partition_count"]):
                        image_data = struct.unpack_from(">32sIIIII", bytes(f.read(0x34)))

                        name_len = 1
                        try:
                            name_len = image_data[0].index(b'\x00')
                        except ValueError:
                            name_len = 28
                        name = str(image_data[0][0:name_len], "ascii", "ignore")

                        image_info = {
                            "partition_name": name,
                            "sector_start": image_data[1],
                            "sector_length": image_data[2],
                            "byte_offset": image_data[1] * 0x200,
                            "byte_length": image_data[2] * 0x200,
                            "partition_type": image_data[3],
                            "unknown1": image_data[4],
                            "unknown2": image_data[5],
                            "files": []
                        }

                        image_info["image_offset"] = image_info["byte_offset"] + 0x4000
                        image_info["image_size"] = image_info["byte_length"] - 0x4000

                        partition_table_info["partitions"].append(image_info)
                else:
                    raise Exception("CompressFS table doesn't match magic")

        return partition_table_info

    def build_compressfs_partition_table(origin, build_info, table_offset, images):
        TABLE_MAGIC = 0x74696D6E

        partition_table_data = bytearray(b'\x00' * 0x6000)

        struct.pack_into(
            ">II",
            partition_table_data,
            0x04,
            len(images),
            TABLE_MAGIC
        )

        struct.pack_into(
            ">II",
            partition_table_data,
            0x2000,
            0x000001B7,
            0x74726170
        )

        partition_entry_offset = 0x0c
        for image in images:
            struct.pack_into(
                ">32sIIIII",
                partition_table_data,
                partition_entry_offset,
                bytes(image["name"], "ascii", "ignore"),
                int(((table_offset + 0x6000 + image["offset"])) / 0x200),
                int((image["size"] + 0x4000) / 0x200),
                0x04, # CompressFS
                0,
                0,
            )

            partition_entry_offset += 0x34

        struct.pack_into(
            ">I",
            partition_table_data,
            0x00,
            build_meta.chunked_checksum(partition_table_data[0x04:(0x0c + (len(images) * 0x34))], 1)
        )

        return partition_table_data
    
    def unpack_compressfs_images(origin, destination, build_info, compressfs_table, silent = False):
        if compressfs_table != None and "partitions" in compressfs_table:
            with open(build_info["path"], "rb") as f:
                for compressfs_image in compressfs_table["partitions"]:
                    f.seek(compressfs_image["image_offset"])

                    if not silent:
                        print("\t\tDump: " + compressfs_image["partition_name"])

                    with open(destination + "/" + compressfs_image["partition_name"] + ".image", "wb") as f2:
                        f2.write(bytes(f.read(compressfs_image["image_size"])))
                        f2.close()

    def tool_nk_unpack(origin, destination, build_info, silent = False, disable_registry_dump = False, read_data = True):
        perl_command_prefix = utv_tools.get_perl_command_prefix()
        tools_path = os.path.abspath("lib/utv-tools/")

        compressed_files = []

        nk_dump_file = "nk.nb"
        nk_dump_file_path = destination + "/" + nk_dump_file

        nk_dump_folder = "level0-nk"
        nk_dump_folder_path = destination + "/" + nk_dump_folder

        nk = {
            "image_file": nk_dump_file,
            "registry_file": "",
            "rom_header": {},
            "files": [],
            "modules": []
        }
        in_modules = False

        if os.path.isdir(nk_dump_folder_path):
            shutil.rmtree(nk_dump_folder_path)

        CECompress = None
        CEDecompress = None

        if read_data:
            if not silent:
                print("\tDumping XIP")
                print("\t\tLoading CECompressv3.dll")

            CECompress, CEDecompress = utv_tools.load_cecompress()

        if not silent:
            print("\t\tCreating swapped NK file")

        build_meta.swap_file_data(origin, nk_dump_file_path, 32, build_info["jump_offset"] - 0x04, build_info["storage_table_offset"])

        if os.path.isfile(nk_dump_file_path):
            if not silent and read_data:
                print("\t\tExtracting XIP")

            process = None
            if not read_data:
                process = Popen([perl_command_prefix, tools_path + "/dumpxip-utv.pl", "-v", "-l", nk_dump_file], cwd=destination, stdout=PIPE)
            else:
                process = Popen([perl_command_prefix, tools_path + "/dumpxip-utv.pl", "-v", "-d=" + nk_dump_folder, nk_dump_file], cwd=destination, stdout=PIPE)

            while True:
                output = process.stdout.readline()

                if output != None:
                    line = str(output.strip(), 'ascii', 'ignore')

                    if read_data:
                        # File names can't have spaces here
                        matches = re.search(r"^\s*0x([a-fA-F0-9]+)\s+(\d+)\s+(\d+\-\d+\-\d+ \d+\:\d+\:\d+)\s+([a-zA-Z0-9\.\-\_]+)\s*$", line, re.IGNORECASE)
                        if matches:
                            file = {
                                "offset": int(matches.group(1), 16),
                                "size": int(matches.group(2)),
                                "time_modified": matches.group(3),
                                "name": matches.group(4),
                                "compressed": False
                            }

                            if in_modules:
                                nk["modules"].append(file)
                            else:
                                nk["files"].append(file)
                        elif re.search(r"^\-\-modules", line, re.IGNORECASE):
                            in_modules = True
                        else:
                            matches = re.search(r"compressed file data\s+([a-zA-Z0-9\.\-\_]+)\s*$", line, re.IGNORECASE)
                            if matches:
                                compressed_files.append(matches.group(1))
                            else:
                                matches = re.search(r"romhdr\s*:\s*(.+)$", line, re.IGNORECASE)
                                if matches:
                                    header_entries = matches.group(1).split(",")

                                    for header_entry in header_entries:
                                        header_keyval = header_entry.strip().split(":")

                                        if len(header_keyval) > 1:
                                            nk["rom_header"][header_keyval[0].strip()] = int(header_keyval[1].strip(), 16)

                    if not silent:
                        print("\t\t\t" + line)

                if process.poll() is not None:
                    break
        else:
            if not silent:
                print("\t\tCouldn't create swapped NK file")

        if read_data:
            if not "default.fdf" in compressed_files and os.path.isfile(nk_dump_folder_path + "/default.fdf"):
                # There's a bug in Windows where this file never gets added because the subprocess pipe doesn't output it to this
                compressed_files.append("default.fdf")

            if len(compressed_files) > 0:
                if not silent:
                    print("\t\tDecompressing files")

                for compressed_file in compressed_files:
                    file_idx = -1
                    file_size = 0
                    
                    for nk_file_idx in range(len(nk["files"])):
                        if nk["files"][nk_file_idx]["name"] == compressed_file:
                            file_idx = nk_file_idx
                            file_size = nk["files"][nk_file_idx]["size"]
                            break

                    if file_idx > -1 and os.path.isfile(nk_dump_folder_path + "/" + compressed_file) and os.path.getsize(nk_dump_folder_path + "/" + compressed_file) != file_size:
                        in_dat = bytearray(open(nk_dump_folder_path + "/" + compressed_file, "rb").read())
                        in_len = len(in_dat)

                        ot_len = in_len * 10
                        ot_dat = bytearray(ot_len)

                        res = CEDecompress(
                            (ctypes.c_char * in_len).from_buffer(in_dat), in_len, 
                            (ctypes.c_char * ot_len).from_buffer(ot_dat), ot_len, 
                            0x00,
                            0x01,
                            0x1000
                        )

                        if res != 0xffffffff:
                            if not silent:
                                print("\t\tWriting decompressed file " + compressed_file + "")

                            nk["files"][nk_file_idx]["compressed"] = True

                            os.remove(nk_dump_folder_path + "/" + compressed_file)

                            open(nk_dump_folder_path + "/" + compressed_file, "wb").write(ot_dat[0:res])
                        else:
                            print("\t\tCouldn't decompress file " + compressed_file + "! Programming error?")

            if not disable_registry_dump:
                if perl_command_prefix == None:
                    if not silent:
                        print("\t\tCouldn't find Perl to further extract NK file")
                else:
                    registry_file_name = "default.reg"
                    packed_registry_file_path = nk_dump_folder + "/default.fdf"
                    if os.path.isfile(destination + "/" + packed_registry_file_path):
                        if not silent:
                            print("\t\tDumping default registry")

                        process = Popen([perl_command_prefix, tools_path + "/fdf2reg.pl", packed_registry_file_path, registry_file_name], cwd=destination, stdout=PIPE)
                        while True:
                            if process.poll() is not None:
                                break

                        if os.path.isfile(destination + "/" + registry_file_name):
                            nk["registry_file"] = registry_file_name

        if not silent:
            print("\tDone.")

        return nk

    def tool_compressfs_unpack(origin, destination, build_info, silent = False, read_data = True, simplify_sizes = False):
        tools_path = os.path.abspath("lib/utv-tools/")

        if not silent:
            print("\tDumping CompressFS images")

        compressfs_table = utv_tools.walk_compressfs_partition_table(origin, build_info)

        if compressfs_table != None and "partition_count" in compressfs_table and compressfs_table["partition_count"] > 0:
            utv_tools.unpack_compressfs_images(origin, destination, build_info, compressfs_table, silent)

            if not silent:
                print("\tDone.")
        else:
            if not silent:
                print("\tNo FS images found")

        if compressfs_table != None and "partitions" in compressfs_table and compressfs_table["partition_count"] > 0:
            if not silent and read_data:
                print("\tDumping CompressFS image files")

            for compressfs_image_idx in range(len(compressfs_table["partitions"])):
                compressfs_image = compressfs_table["partitions"][compressfs_image_idx]

                compressfs_image_name = compressfs_image["partition_name"] + ".image"
                compressfs_image_path = destination + "/" + compressfs_image_name

                if os.path.isfile(compressfs_image_path):
                    compressfs_dump_path = destination + "/level0-compressfs/"

                    if not os.path.isdir(compressfs_dump_path) and read_data:
                        os.makedirs(compressfs_dump_path, 0o777, True)

                        if not os.path.isdir(compressfs_dump_path):
                            raise Exception("Couldn't create dump folder '" + compressfs_dump_path + "'")

                    if not silent:
                        if not read_data:
                            print("\t\tList: " + compressfs_image["partition_name"] + ".image")
                        else:
                            print("\t\tUnpack: " + compressfs_image["partition_name"] + ".image")

                    process = None
                    if not read_data:
                        process = Popen(utv_tools.resolve_executable_command([tools_path + "/utvimage-mod.exe", compressfs_image_name]), cwd=destination, stdout=PIPE)
                    else:
                        process = Popen(utv_tools.resolve_executable_command([tools_path + "/utvimage-mod.exe", "../" + compressfs_image_name]), cwd=compressfs_dump_path, stdout=PIPE)
                    while True:
                        output = process.stdout.readline()

                        if output != None and not silent:
                            line = str(output.strip(), 'ascii', 'ignore')

                            if re.search(r"^[\/\\]", line, re.IGNORECASE):
                                if not read_data:
                                    file_path = destination + "/" + line

                                    if not os.path.isdir(file_path):
                                        data_size = os.path.getsize(file_path)

                                        size = "0B"
                                        if simplify_sizes:
                                            size = build_meta.simplify_size(data_size)
                                        else:
                                            size = str(data_size) + "B"

                                        print("\t\t\t" + line + "\t(" + size + ")")
                                    else:
                                        print("\t\t\t" + line)
                                else:
                                    file = {
                                        "path": line,
                                    }

                                    file_path = compressfs_dump_path + "/" + compressfs_image["partition_name"] + ".image/" + line

                                    if not os.path.isdir(file_path):
                                        file["name"] = os.path.basename(file_path)
                                        file["size"] = os.path.getsize(file_path)

                                    compressfs_table["partitions"][compressfs_image_idx]["files"].append(file)

                                    print("\t\t\t" + line)

                        if process.poll() is not None:
                            break

                    if read_data:
                        image_folder_files = listdir(compressfs_dump_path + "/" + compressfs_image_name)

                        if len(image_folder_files) == 1:
                            shutil.move(compressfs_dump_path + "/" + compressfs_image_name + "/" + image_folder_files[0], compressfs_dump_path + "/" + image_folder_files[0])

                            shutil.rmtree(compressfs_dump_path + "/" + compressfs_image_name)


                            

            if not silent:
                print("\tDone.")

        return compressfs_table

    def pack_utv_header(build_info):
        header_data = bytearray(b'\x00' * 0x1000)

        struct.pack_into(
            ">IIIIIIIIIIIIII",
            header_data,
            0x00,
            0x10000400,
            0x00000000,
            0x00,
            build_info["build_size"] >> 0x02, # Build size
            build_info["code_size"] >> 0x02, # Code size
            build_info["build_version"],
            0x00000000,
            0x00000000,
            0x00000000,
            0x4E6F4653, # NoFS
            0x00000000,
            0x00000000,
            build_info["build_address"],
            build_info["build_flags"]
        )

        return header_data

    def tool_nk_pack(origin, destination, build_info, silent = False, disable_registry_build = False):
        perl_command_prefix = utv_tools.get_perl_command_prefix()
        tools_path = os.path.abspath("lib/utv-tools/")

        tmp_dump_path = tempfile.mktemp()
        os.makedirs(tmp_dump_path, 0o777, True)
        if not os.path.isdir(tmp_dump_path):
            raise Exception("Couldn't create tmp folder")

        if not silent:
            print("\tCreating NK image")
            print("\t\tLoading CECompressv3.dll")

        CECompress, CEDecompress = utv_tools.load_cecompress()

        nk_files_folder_name = "level0-nk"
        nk_files_path = origin + "/" + nk_files_folder_name

        registry_file_name = "default.reg"
        registry_file_path = origin + "/" + registry_file_name
        packed_registry_file_path = nk_files_folder_name + "/default.fdf"
        if not disable_registry_build and os.path.isfile(registry_file_path):
            if perl_command_prefix == None:
                if not silent:
                    print("\t\tCouldn't find Perl to further extract NK file")
            elif not silent:
                print("\t\tBuilding default registry")

                process = Popen([perl_command_prefix, tools_path + "/reg2fdf.pl", "-3", registry_file_name, packed_registry_file_path], cwd=origin, stdout=PIPE)
                while True:
                    if process.poll() is not None:
                        break

        nk_files = listdir(nk_files_path)
        compressed_files = {}
        nk_data = bytearray(b'')
        for name in nk_files:
            nk_file_path = nk_files_path + "/" + name

            if re.search(r"\.(dll|exe)$", name, re.IGNORECASE) or re.search(r"^data_0x[0-9a-fA-F]+_0x[0-9a-fA-F]+.bin$", name, re.IGNORECASE) or re.search(r"^data_0x[0-9a-fA-F]+_0x[0-9a-fA-F]+_.+?.bin$", name, re.IGNORECASE):
                shutil.copy(nk_file_path, tmp_dump_path + "/" + name)
            else:
                in_dat = bytearray(open(nk_file_path, "rb").read())
                in_len = len(in_dat)

                ot_len = in_len * 10
                ot_dat = bytearray(ot_len)

                res = CECompress(
                    (ctypes.c_char * in_len).from_buffer(in_dat), in_len,
                    (ctypes.c_char * ot_len).from_buffer(ot_dat), ot_len,
                    0x01,
                    0x1000
                )

                if res != 0xffffffff and in_len > res:
                    open(tmp_dump_path + "/" + name, "wb").write(bytearray(ot_dat[0:res]))

                    compressed_files[name] = in_len
                else:
                    shutil.copy(nk_file_path, tmp_dump_path + "/" + name)


        if not silent:
            print("\t\tBuilding XIP")

        tmp_nk_path = tempfile.mktemp()

        nk_base_address = 0
        if "wince_romhdr_physfirst" in build_info and build_info["wince_romhdr_physfirst"] > 0:
            nk_base_address = build_info["wince_romhdr_physfirst"]
        else:
            nk_base_address = build_info["build_address"] + 0x1000
        
        user_specs = []
        if "wince_romhdr_dllfirst" in build_info and build_info["wince_romhdr_dllfirst"] > 0:
            user_specs += ["-v", "dllfirst=" + str(build_info["wince_romhdr_dllfirst"])]
        if "wince_romhdr_dlllast" in build_info and build_info["wince_romhdr_dlllast"] > 0:
            user_specs += ["-v", "dlllast=" + str(build_info["wince_romhdr_dlllast"])]
        if "wince_romhdr_ramstart" in build_info and build_info["wince_romhdr_ramstart"] > 0:
            user_specs += ["-v", "ulRAMStart=" + str(build_info["wince_romhdr_ramstart"])]
        if "wince_romhdr_ramfree" in build_info and build_info["wince_romhdr_ramfree"] > 0:
            user_specs += ["-v", "ulRAMFree=" + str(build_info["wince_romhdr_ramfree"])]
        if "wince_romhdr_ramend" in build_info and build_info["wince_romhdr_ramend"] > 0:
            user_specs += ["-v", "ulRAMEnd=" + str(build_info["wince_romhdr_ramend"])]
        if "wince_romhdr_kernelflags" in build_info and build_info["wince_romhdr_kernelflags"] > 0:
            user_specs += ["-v", "ulKernelFlags=" + str(build_info["wince_romhdr_kernelflags"])]
        if "wince_romhdr_fsrampercent" in build_info and build_info["wince_romhdr_fsrampercent"] > 0:
            user_specs += ["-v", "ulFSRamPercent=" + str(build_info["wince_romhdr_fsrampercent"])]
        if "wince_romhdr_uscputype" in build_info and build_info["wince_romhdr_uscputype"] > 0:
            user_specs += ["-v", "usCPUType=" + str(build_info["wince_romhdr_uscputype"])]
        if "wince_romhdr_usmiscflags" in build_info and build_info["wince_romhdr_usmiscflags"] > 0:
            user_specs += ["-v", "usMiscFlags=" + str(build_info["wince_romhdr_usmiscflags"])]
        if "wince_romhdr_address" in build_info and build_info["wince_romhdr_address"] > 0:
            user_specs += ["-v", "prevROMHDRAddy=" + str(build_info["wince_romhdr_address"])]

        compress_file_param = ','.join('{}={}'.format(key, val) for key, val in compressed_files.items())
        process = Popen([perl_command_prefix, tools_path + "/makexip-utv.pl", "-c", compress_file_param] + user_specs + [hex(nk_base_address)[2:], tmp_dump_path, tmp_nk_path], cwd=origin, stdout=PIPE)
        while True:
            output = process.stdout.readline()

            if output != None and not silent:
                line = str(output.strip(), 'ascii', 'ignore')

                if line != "":
                    print("\t\t\t" + line)

            if process.poll() is not None:
                break

        if os.path.isfile(tmp_nk_path):
            nk_data = bytearray(open(tmp_nk_path, "rb").read())

            nk_data = build_meta.swap_data(nk_data, 32)

            os.remove(tmp_nk_path)
        else:
            raise Exception("Couldn't create NK file '" + tmp_nk_path + "'")

        if tmp_dump_path != None and os.path.isdir(tmp_dump_path):
            shutil.rmtree(tmp_dump_path)

        return nk_data

    def tool_compressfs_pack(origin, destination, build_info, table_offset = 0x00, silent = False):
        tools_path = os.path.abspath("lib/utv-tools/")

        tmp_dump_path = tempfile.mktemp()
        os.makedirs(tmp_dump_path, 0o777, True)
        if not os.path.isdir(tmp_dump_path):
            raise Exception("Couldn't create tmp folder")

        if not silent:
            print("\tCreating CompressFS images")

        compressfs_absolute_path = os.path.abspath(origin + "/level0-compressfs")
        objects = listdir(compressfs_absolute_path)

        images = []
        partition_data = b''
        for image_folder_name in objects:
            image_name = re.sub(".image", "", image_folder_name, flags=re.IGNORECASE)
            buildfsimage_script_name = image_folder_name + ".bfs"
            buildfsimage_script_path = tmp_dump_path + "/" + buildfsimage_script_name
            fsimage_path = tmp_dump_path + "/" + image_folder_name

            volume_name = "VOLUME" + str(random.randint(0, 0xFFFF)) if not image_name else image_name
            volume_path = ""
            volume_folders = listdir(compressfs_absolute_path + "/" + image_folder_name)
            if len(volume_folders) == 1:
                for volume_folder_name in listdir(compressfs_absolute_path + "/" + image_folder_name):
                    if os.path.isdir(compressfs_absolute_path + "/" + image_folder_name + "/" + volume_folder_name):
                        volume_name = volume_folder_name
                        volume_path = "/" + volume_name

            buildfsimage_script = ""
            buildfsimage_script += "Addvolume " + volume_name + "\n"
            buildfsimage_script += "addtree " + compressfs_absolute_path + "/" + image_folder_name + volume_path + "\n"
            buildfsimage_script += "setattrs -maxsegmentsize 4096\n"

            open(buildfsimage_script_path, "wb").write(bytearray(buildfsimage_script, 'ascii', 'ignore'))

            if not silent:
                print("\t\tPack: " + image_folder_name)

            process = Popen(utv_tools.resolve_executable_command([tools_path + "/buildfsimage.exe", "-script", buildfsimage_script_name, "-output", fsimage_path]), cwd=tmp_dump_path, stdout=PIPE)
            while True:
                output = process.stdout.readline()

                if output != None and not silent:
                    line = str(output.strip(), 'ascii', 'ignore')

                    if line != "":
                        print("\t\t\t" + line)

                if process.poll() is not None:
                    break

            if os.path.isfile(fsimage_path):
                image = {
                    "name": image_name.lower(),
                    "path": fsimage_path,
                    "offset": len(partition_data),
                    "size": 0,
                }

                partition_start_data = bytearray(0x4000)
                struct.pack_into(
                    ">I",
                    partition_start_data,
                    0x04,
                    0x74726170
                )

                # This can be hardcoded since the data is static but doing this anyway.
                struct.pack_into(
                    ">I",
                    partition_start_data,
                    0x00,
                    build_meta.chunked_checksum(partition_start_data[0x04:], 1)
                )

                image_data = open(fsimage_path, "rb").read()

                partition_data += partition_start_data + image_data

                padding = b''
                padding_size = (0x200 - (len(partition_data) % 0x200))
                if padding_size < 0x200:
                    padding = b'eMac' * max((math.ceil(padding_size >> 2) + 1), 1)
                    padding = padding[0:padding_size]

                partition_data += padding

                image["size"] = len(partition_data) - image["offset"]

                images.append(image)
            else:
                print("\t\tWARNING: couldn't find '" + name + "'")

        partition_table_data = utv_tools.build_compressfs_partition_table(origin, build_info, table_offset, images)

        if not silent:
            print("\tDone.")

        if tmp_dump_path != None and os.path.isdir(tmp_dump_path):
            shutil.rmtree(tmp_dump_path)

        return partition_table_data + partition_data

    def list(origin, disable_nk_list = False, disable_compressfs_list = False, simplify_sizes = False):
        tmp_path = tempfile.mktemp()

        if not os.path.isdir(tmp_path):
            os.makedirs(tmp_path, 0o777, True)

            if not os.path.isdir(tmp_path):
                raise Exception("Destination doesn't exist")

        build_info = build_meta.detect(origin)

        if not disable_nk_list:
            print("\n=== NK Files ===\n")

            utv_tools.tool_nk_unpack(origin, tmp_path, build_info, False, True, False)

        if not disable_compressfs_list:
            print("\n\n=== CompressFS Files ===\n")

            utv_tools.tool_compressfs_unpack(origin, tmp_path, build_info, False, False, simplify_sizes)

        if os.path.isdir(tmp_path):
            shutil.rmtree(tmp_path)

    def unpack(origin, destination = "./out", silent = False, create_descriptor_file = True, disable_nk_dump = False, disable_compressfs_dump = False, disable_registry_dump = False):
        if not os.path.isdir(destination):
            os.makedirs(destination, 0o777, True)

            if not os.path.isdir(destination):
                raise Exception("Destination doesn't exist")

        shutil.copy(origin, destination + "/template.bin")

        build_info = build_meta.detect(origin)

        descriptor_table = {
            "origin": origin,
            "level0_build_info": build_info,
            "level0_nk_objects": {},
            "level0_compressfs_objects": {},
            "destination": destination,
            "template_file": "template.bin",
        }

        if not silent:
            build_meta.print_build_info(build_info)

        if not disable_nk_dump:
            descriptor_table["level0_nk_objects"] = utv_tools.tool_nk_unpack(origin, destination, build_info, silent, disable_registry_dump)

        if not disable_compressfs_dump:
            descriptor_table["level0_compressfs_objects"] = utv_tools.tool_compressfs_unpack(origin, destination, build_info, silent)

        if create_descriptor_file:
            with open(destination + "/dt.json", "w") as f:
                f.write(json.dumps(descriptor_table, sort_keys=True, indent=4))
                f.close()

    def pack(origin, out_path = "./out.o", source_build_path = None, silent = False, build_info = None, use_descriptor_file = True, disable_compressfs_build = False, disable_nk_build = False, disable_registry_build = False):
        if build_info == None and source_build_path != None:
            build_info = build_meta.detect(source_build_path)

        descriptor_table_path = origin + "/dt.json"
        descriptor_table = None
        if use_descriptor_file and os.path.isfile(descriptor_table_path):
            descriptor_table = json.loads(build_meta.get_file_data(descriptor_table_path).decode())

        if build_info == None:
            if descriptor_table != None and "level0_build_info" in descriptor_table:
                build_info = level0_build_info["level0_build_info"]
            else:
                build_info = build_meta.default_build_info(out_path)

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
            build_meta.print_build_info(build_info)

        nk_data = b''
        compressfs_data = b''

        if not disable_nk_build:
            nk_data = utv_tools.tool_nk_pack(origin, out_path, build_info, silent, disable_registry_build)
        else:
            nk_data = build_meta.get_file_data(build_info["source_build_path"], 0x1000, build_info["code_size"])

        build_nk_size = len(nk_data)

        nk_data += bytearray(build_meta.align(len(nk_data)))

        padded_nk_size = len(nk_data)
        
        if not disable_compressfs_build:
            compressfs_data = utv_tools.tool_compressfs_pack(origin, out_path, build_info, (0x1000 + padded_nk_size), silent)
        else:
            compressfs_data = build_meta.get_file_data(build_info["source_build_path"], build_info["storage_table_offset"])

            if build_info["build_size"] > (0x1000 + padded_nk_size):
                nk_data += bytearray(build_info["code_size"] - len(nk_data))
            elif build_info["build_size"] < (0x1000 + padded_nk_size):
                print("!!! NK IMAGE GOES BEYOND COMPRESSFS OFFSET. build_size=" + hex(build_info["code_size"]) + ", . THERE MAY BE A PROBLEM ACCESSING THE COMPRESSFS TABLE. THIS CAN HAPPEN WHEN YOU DISABLE BUILDING A COMPRESSFS IMAGE BUT DECIDE TO EXPAND THE NK IMAGE. !!!")

        build_info["code_size"] = len(nk_data)
        build_info["build_size"] = 0x1000 + build_info["code_size"]

        build_header = utv_tools.pack_utv_header(build_info)
            
        box_build = build_header + nk_data + compressfs_data

        struct.pack_into(
            ">I",
            box_build,
            0x08,
            build_meta.checksum(box_build[0:build_info["code_size"]])
        )

        build_meta.write_object_file(build_info, box_build, silent)
