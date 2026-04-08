#!/usr/bin/python

import argparse
import binascii
import struct
import os
from pathlib import Path
from enum import Enum
import zlib
from dataclasses import dataclass, field
import hashlib
from datetime import datetime
import re

class BLOCK_COMPRESSION_TYPE(int, Enum):
    NONE = 0
    LZSS = 1 # not supported in this file but it's the same algorithm on the original WebTV
    ZLIB = 2

    def __str__(self):
        return str(self.name)
        
    @classmethod
    def has_name(self, name):
        return hasattr(self, name.upper())

    @classmethod
    def has_value(self, value):
        return value in self._value2member_map_

    @classmethod
    def get_value(self, name):
        return getattr(self, name)

@dataclass
class UpgradePartMeta:
    file_name: str
    file_md5: bytes
    file_size: int
    uncompressed_size: int
    compression_type: BLOCK_COMPRESSION_TYPE

    def __str__(self):
        # ^(.{1,12}) ([0-9a-fA-F]{1,8} [0-9a-fA-F]{1,8} [0-9a-fA-F]{1,8} [0-9a-fA-F]{1,8}) ([0-9a-fA-F]{1,8}) ([0-9a-fA-F]{1,8}) ([0-9a-fA-F]{1,8} [0-9]+)

        # First group is the part file name must be 1 to 12 chars (probably 8.3 naming) in UpdateDownload.dll. BIOS allows up to 32.
        # Second group is the MD5 of the file split into 4 32-bit hex numbers.
        # Third is the downloaded compressed file size, must be non-zero and 512Kb or less
        # Fourth is uncompressed file size, must be non-zero
        # Fifth is the compression type must be 0=no compression, 1=LZSS or 2=ZLIB

        # Split the MD5 into 4 32-bit groups, reverse the endian so the box can read it properly then display as a 4 groups of hex strings
        split_md5 = " ".join(self.file_md5[i:i+4][::-1].hex().upper() for i in range(0, 16, 4))

        content = f"{self.file_name} {split_md5} {self.file_size:08X} {self.uncompressed_size:08X} {int(self.compression_type):02X}\n"

        return content

@dataclass
class UpgradeMeta:
    name: str
    build_number: int
    build_version: str
    date: datetime
    partition_size: int
    package_size: int
    package_file_count: int
    parts: list[UpgradePartMeta] = field(default_factory=list)

    # PKG.DIR file contents
    def __str__(self):
        content = ""

        version_parts = (self.build_version.split('.') + ['0'] * 2)[:2]
        version_hex = "".join(f"{int(version_part):04X}" for version_part in version_parts)

        # ^NAME:\s(.{1,511})\n
        content += f"NAME: {self.name}\n"; # Name can be up to 511 chars
        # ^BUILD:\s([0-9a-fA-F]{1,8})\s([0-9a-fA-F]{1,8})
        # Both UpdateDownload.dll and the BIOS allows for anything after the two build hex numbers
        # The build number is checked at the very end (at 99%) to make sure it matches what's in the BOOT.SIG or TBOOT.SIG file.
        content += f"BUILD: {self.build_number:08X} {version_hex}\n"; # Upgrade build version info. First hex number looks like a build number, second number looks like a version number in hex
        # ^DATE:\(s[0-9]+)\S([0-9]+)\S([0-9]+).*\n$
        # UpdateDownload.dll requres the entire date string to be up to 511 characters. Must be any parsable date (not sure whay library they use to parse)
        # The bios makes sure the year is greater than 2002, any non-whitespace char can be used to separate the month, day and year (in that order) and anything after that is't checked.
        content += f"DATE: " + self.date.strftime("%m/%d/%Y %H:%M:%S.%f")[:-4] + "\n"; # Date built?
        # ^PARTITION:\s([0-9a-fA-F]{1,8})\n$
        # The bios allows for anything after the hex number, UpdateDownload.dll does not
        content += f"PARTITION: {self.partition_size:08X}\n"; # Size of the FAT paritition that stores the files in this package. Needs to be == 32002048 bytes although there's a lot of code to reach this conclusion, not sure why.
        # ^([0-9a-fA-F]{1,8})\n$
        # The bios allows for anything after the hex number, UpdateDownload.dll does not
        content += f"{len(self.parts):08X}\n"; # Download part count
        # ^([0-9a-fA-F]{1,8})\n$
        # The bios allows for anything after the hex number, UpdateDownload.dll does not
        content += f"{self.package_size:08X}\n"; # Size of the file package
        # ^([0-9a-fA-F]{1,8})\n$
        # The bios allows for anything after the hex number, UpdateDownload.dll does not
        content += f"{self.package_file_count:08X}\n"; # Unknown? My guess is it's number of files in the package. This isn't used to generate the boot partition.

        # What follows is a list of files for each part

        for part in self.parts:
            content += str(part)

        # ^#([0-9a-fA-F]{1,8}) ([0-9a-fA-F]{1,8} [0-9a-fA-F]{1,8} [0-9a-fA-F]{1,8} [0-9a-fA-F]{1,8})
        # It must start with a #
        # We start at offset 0 of PKG.DIR and the first group is the size from that point we use to hash the file
        # Second group is the MD5 hash of the PKG.DIR up to the size we specified. We can't hash the entire file since we're also writing this MD5 line which we don't know prior.

        # MD5 all the PKG.DIR content before this. a "#LEN MD5" line will be the last line of the PKG.DIR file
        content_md5 = hashlib.md5(content.encode('ascii')).digest()

        # Split the MD5 into 4 32-bit groups, reverse the endian so the box can read it properly then display as a 4 groups of hex strings
        split_md5 = " ".join(content_md5[i:i+4][::-1].hex().upper() for i in range(0, 16, 4))

        content += f"#{len(content):08X} {split_md5}\n"

        return content


class Msntv2GenDr:

    PARTITION_SIZE     = 32002048
    FILEPKG_MIN_SIZE   = 1
    FILEPKG_MAX_SIZE   = 32000000
    FILEPKG_MAX_FILES  = 500
    # The .SIG files contain the MD5s of the other files in the package, those MD5s are generated using msntv2-sigmd5.py individually
    # It's a manual process at the moment. I might integrate this into Rommy at some point.
    # The .SIG file is also protected with an RSA SHA1 signature, which will need a modified BIOS that doesn't check that, some other bypass or the actual private keys (which we don't have as far as I know).
    FILEPKG_SIG_FIXES  = ["BOOT.SIG", "TBOOT.SIG"]
    FILEPKG_REQ_FILES  = [FILEPKG_SIG_FIXES, "NK.BIN"]
    PKGDIR_NAME        = "PKG.DIR"
    GEN_PART_MAX_SIZE  = 256000
    PART_MAX_SIZE      = 524288
    MAX_PART_COUNT     = 500
    PART_NAME_TEMPLATE = "PART{:03d}.DAT"

    DEFAULT_OUT_PATH         = "./"
    DEFAULT_NAME             = "Some Cool Upgrade"
    DEFAULT_BUILD_NUMBER     = 6969
    DEFAULT_VERSION_NUMBER   = "1.1"
    DEFAULT_DATE             = "09/03/2013 04:20:06.69"
    DEFAULT_PART_COUNT       = -1
    DEFAULT_COMPRESSION_TYPE = BLOCK_COMPRESSION_TYPE.ZLIB

    silent = False
    in_path = None
    out_path = DEFAULT_OUT_PATH
    name = DEFAULT_NAME
    build_number = None
    version_number = None
    date = None
    part_count = DEFAULT_PART_COUNT
    compression_type = DEFAULT_COMPRESSION_TYPE

    def __init__(self):
        allowed_compression_types = [
            BLOCK_COMPRESSION_TYPE.NONE,
            BLOCK_COMPRESSION_TYPE.ZLIB
        ]

        description = "MSNTV2 DR TOOL: "
        description += "This tool creates the PKG.DIR and part files so the MSNTV2 can build the boot partition when it's in a disaster recovery state."

        epilog = "Special thanks to WebTV hacking community! Have a --farted day!"

        ap = argparse.ArgumentParser(description=description, epilog=epilog)

        ap.add_argument('--silent', '-q', action='store_true',
                        help="Don't print anything unless it's a fatal exception.")

        ap.add_argument('--name', '-n', type=str,
                        help=f"The name of the upgrade. Will be '{self.DEFAULT_NAME}' if nothing was specified.")

        ap.add_argument('--build-number', '-b', type=int,
                        help=f"The build number of the upgrade. Will be either what's found in the BOOT.SIG or TBOOT.SIG file or {self.DEFAULT_BUILD_NUMBER} if nothing was specified. NOTE: the MSNTV2 checks this to make sure it matches what's defined in the signature file.")

        ap.add_argument('--version-number', '-v', type=str,
                        help=f"The version number of the upgrade in the format #.#. Will be either what's found in the BOOT.SIG or TBOOT.SIG file or {self.DEFAULT_VERSION_NUMBER} if nothing was specified.")

        ap.add_argument('--date', '-d', type=str,
                        help=f"The date the upgrade in the format MM/DD/YYYY HH:MM:SS.SS. The year must be greater than 2002. Will be either what's found in the BOOT.SIG or TBOOT.SIG file, the date of NK.BIN file in the input directory or {self.DEFAULT_DATE} if nothing was specified.")

        ap.add_argument('--part-count', '-p', type=int,
                        help=f"The number of parts to generate. This will be accepted if the count is {self.MAX_PART_COUNT} or less and the individual parts don't exceed {self.PART_MAX_SIZE} bytes. The part count is auto-generated if nothing was specified.")

        ap.add_argument('--compression-type', '-c', type=str,
                        help=f"The type of compression to use on the parts. Will be {self.DEFAULT_COMPRESSION_TYPE} if nothing was specified. Allowed types: " + ", ".join(item.name for item in allowed_compression_types))

        ap.add_argument('--farted', '-f', action='store_true',
                        help="Let 'er rip a lovely one!")

        ap.add_argument('IN_PATH', type=str,
                        help=f"Directory path to the list of files to add to the boot partition. The directory must contain a NK.BIN and a BOOT.SIG or TBOOT.SIG file, files need to be named in the 8.3 format, must have {self.FILEPKG_MAX_FILES} or less files and the combined files cannot exceed {self.FILEPKG_MAX_SIZE} bytes.")

        ap.add_argument('OUT_PATH', type=str, nargs='?',
                        help="Directory path to output the files to. It will output to the current directory if nothing is specified.")

        arg = ap.parse_args()

        self.silent = arg.silent

        if arg.IN_PATH != None:
            self.in_path = arg.IN_PATH

            self.validate_input_directory()
        else:
            raise Exception(f"You must specify an input directory path!")

        if arg.OUT_PATH != None:
            self.out_path = arg.OUT_PATH

        if arg.name != None:
            self.name = arg.name

        if arg.build_number != None:
            self.build_number = arg.build_number

        if arg.version_number != None:
            self.version_number = arg.version_number

        if arg.date != None:
            self.date = arg.date

        if arg.part_count != None:
            self.part_count = arg.part_count

            if self.part_count > self.MAX_PART_COUNT:
                raise Exception(f"The part count '{self.part_count}' is too high!")

        if arg.compression_type != None:
            _compression_type = arg.compression_type.upper()

            if not _compression_type in BLOCK_COMPRESSION_TYPE.__members__ or not BLOCK_COMPRESSION_TYPE[_compression_type] in allowed_compression_types:
                raise Exception("Compression type '" + _compression_type + "' is not known. Allowed types: " + ", ".join(item.name for item in allowed_compression_types))
            else:
                self.compression_type = BLOCK_COMPRESSION_TYPE[_compression_type]

        self.generate()

        if arg.farted:
            self.do_fart()

    def log(self, *args, **kwargs):
        if not self.silent:
            print(*args, **kwargs)

    def strtodatetime(self, date_str):
        possible_date_formats = [
            "%m/%d/%Y %H:%M:%S.%f",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y",
            "%m-%d-%Y %H:%M:%S.%f",
            "%m-%d-%Y %H:%M:%S",
            "%m-%d-%Y",
            "%Y/%m/%d %H:%M:%S.%f",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

        for date_format in possible_date_formats:
            try:
                return datetime.strptime(date_str, date_format)
            except ValueError:
                pass
        raise ValueError(f"Invalid date format: '{date_str}'")

    def validate_input_directory(self):
        in_path = Path(self.in_path)

        if os.path.isdir(self.in_path):
            in_size = sum(file.stat().st_size for file in in_path.iterdir() if file.is_file())

            if in_size > self.FILEPKG_MAX_SIZE:
                raise Exception(f"The total of all the files in '{self.in_path}' is too large. It must be smaller than {self.FILEPKG_MAX_SIZE} bytes")
            elif in_size < self.FILEPKG_MIN_SIZE:
                raise Exception(f"The total of all the files in input path '{self.in_path}' is too small!")

            in_files = [file.name.upper() for file in in_path.iterdir() if file.is_file()]

            if len(in_files) > self.FILEPKG_MAX_FILES:
                raise Exception(f"The file count in '{self.in_path}' cannot exceed {self.FILEPKG_MAX_FILES}!")

            for req_item in self.FILEPKG_REQ_FILES:
                if isinstance(req_item, list):
                    if not any(req_file.upper() in in_files for req_file in req_item):
                        raise Exception(f"The input path '{self.in_path}' must have one of the {req_item} files!")
                else:
                    if req_item.upper() not in in_files:
                        raise Exception(f"The input path '{self.in_path}' must have the '{req_item}' file!")

            for in_file in in_files:
                if not re.match(r'^[A-Z0-9]{1,8}(\.[A-Z0-9]{0,3})?$', in_file):
                    raise Exception(f"The input file '{in_file}' doesn't follow the 8.3 file name format!")

        else:
            raise Exception(f"The input path '{self.in_path}' must be a directory and exist!")

    # The signature file isn't generated here but this is what I can make of the format based on what I see in the BIOS code:
    #
    # - The signature file is named BOOT.SIG or TBOOT.SIG. BOOT.SIG is the only file we've seen in retail images. TBOOT.SIG probably is used in test builds.
    # - There's a RSA SHA1 signature on the first line. It's used to validate the file based on a SHA1 of the lines after the first line. The first line is encrypted with a private key that we don't have. Public keys are stored in the BIOS.
    # - The build version is validated after upgrade download to see if it matches what's in the PKG.DIR file.
    # - The signature file can check multiple files (each on its own line) but I've only seen the NK.BIN file in retail images.
    # - File validation after update happens in the BIOS function 0x00822280 which takes a signature object parameter from function 0x00822cc8
    # - There's no RSA signature check like the original boxes so it's much simpler to bypass.
    # - Keywords in file parsing are: "mM", "xX", "bB", "uU", "DEV", "FACT", and "SIGNSUB:" I didn't look at all of them but someone else can.
    #
    # Format:
    #     RSA_SHA1_SIGNATURE_BLOCK?
    #     UNKNOWN?_BUILD_FLAGS? BUILDER_CONTACT? BUILD_DATE
    #     BUILD_NUMBER BUILD_VERSION SIGNSUB: SIGNATURE_SUBMITTER_CONTACT?
    #     8.3_FILE_NAME FILE_SIZE FILE_MD5[0] FILE_MD5[1] FILE_MD5[2] FILE_MD5[3] UNKNOWN?_FILE_TYPE? # THREE_POINT_MD5[0] THREE_POINT_MD5[1] THREE_POINT_MD5[2] THREE_POINT_MD5[3]
    #
    # - The "THREE_POINT_MD5" is an MD5 of part of the file but in three sections. Essentially the MD5 of 768 bytes=[first 256 bytes + middle 256 btytes + last 256 bytes]. You can see this algorithm in BIOS function 0x00806108
    # - If the file is small enough then it'll MD5 the entire file.
    # - The UNKNOWN?_FILE_TYPE? might signal which file to load for boot? Possible values _might_ be M, X, B, or U. Might unlock some functionality. Code is in the BIOS if interested, this doesn't seem important to what I'm trying to do at the moment.
    # - The FILE_MD5 is used after an update and THREE_POINT_MD5 is used on every boot. Makes sense since the THREE_POINT_MD5 is faster to validate.
    #
    # NOTE: there also seems to be an EBOOT.SIG but it isn't checked in most places. So code may have been removed. Might be related to dev/engineering
    #
    def get_signature_metadata(self):
        sig_build_numer = None
        sig_version_number = None
        sig_date = None

        in_path = Path(self.in_path)
        in_sig_files = [file.name for file in in_path.iterdir() if file.is_file() and file.name.upper() in self.FILEPKG_SIG_FIXES]

        if in_sig_files:
            # Will use the first signature file found to capture the build version information
            sig_contents = open(f"{self.in_path}/{in_sig_files[0]}", "r").read()

            sig_buildvers_match = re.search(r"([0-9A-Fa-f]{8})\s+([0-9A-Fa-f]{8})\s+SIGNSUB:", sig_contents)
            if sig_buildvers_match:
                sig_buildvers_hex = sig_buildvers_match.groups()

                sig_build_numer = int(sig_buildvers_hex[0], 16)

                sig_major_version = int(sig_buildvers_hex[1][:4], 16)
                sig_minor_version = int(sig_buildvers_hex[1][4:], 16)
                sig_version_number = f"{sig_major_version}.{sig_minor_version}"

            sig_date_match = re.search(r"\w+ (\d+/\d+/\d+ \d+:\d+:\d+.?\d*)", sig_contents)
            if sig_date_match:
                sig_date = sig_date_match.groups()[0]

        return sig_build_numer, sig_version_number, sig_date

    def generate(self):
        package_blob = self.generate_package()

        if self.build_number == None or self.version_number == None or self.date == None:
            sig_build_numer, sig_version_number, sig_date = self.get_signature_metadata()

            if self.build_number == None:
                if sig_build_numer != None:
                    self.build_number = sig_build_numer
                else:
                    self.build_number = self.DEFAULT_BUILD_NUMBER

            if self.version_number == None:
                if sig_version_number != None:
                    self.version_number = sig_version_number
                else:
                    self.version_number = self.DEFAULT_VERSION_NUMBER

            if self.date == None:
                if sig_date != None:
                    self.date = sig_date
                else:
                    in_path = Path(self.in_path)
                    in_nkbin_files = [file.name for file in in_path.iterdir() if file.is_file() and file.name.upper() == "NK.BIN"]
                    if in_nkbin_files:
                        self.date = datetime.fromtimestamp(os.path.getmtime(f"{self.in_path}/{in_nkbin_files[0]}")).strftime("%m/%d/%Y %H:%M:%S.%f")[:-4]
                    else:
                        self.date = self.DEFAULT_DATE

        upgrade = UpgradeMeta(
            name = self.name,
            build_number = self.build_number,
            build_version = self.version_number,
            date = self.strtodatetime(self.date),
            partition_size = self.PARTITION_SIZE,
            package_size = len(package_blob),
            package_file_count = 0,
            parts = self.generate_parts(package_blob)
        )

        self.log(f"Creating {self.PKGDIR_NAME}")

        open(f"{self.out_path}/{self.PKGDIR_NAME}", "w").write(str(upgrade))

        self.log(f"Done! Files placed in the '{self.out_path}' directory.")

    def generate_parts(self, file_pkg):
        self.log("Creating parts...")

        # The parts are just the package file split up, obfuscated using a simple algorithm and compressed
        # The compression algorithm used is defined in the PKG.DIR file which has metadata for the entire download

        pkg_size = len(file_pkg)

        if self.part_count <= 0:
            self.part_count = self.generate_part_count(pkg_size)

        part_size = pkg_size // self.part_count
        part_size_remainder = pkg_size % self.part_count

        self.log(f"Part count is {self.part_count}, making each part ~ {part_size} bytes in size (before compression)...")

        blob_start_index = 0
        parts = []
        for part_index in range(self.part_count):
            part_filename = self.PART_NAME_TEMPLATE.format(part_index)

            blob_end_index = blob_start_index + part_size

            if part_size_remainder > part_index:
                blob_end_index += 1

            part_uncompressed_data = self.obfuscate_part_data(bytearray(file_pkg[blob_start_index:blob_end_index]))
            part_uncompressed_size = len(part_uncompressed_data)

            part_final_data = bytearray()
            part_final_size = 0

            if self.compression_type == BLOCK_COMPRESSION_TYPE.ZLIB:
                part_final_data = zlib.compress(part_uncompressed_data, 9)
                part_final_size = len(part_final_data)

                self.log(f"\tWriting {part_filename} with size {part_final_size} bytes ({(1 - (part_final_size/part_uncompressed_size)):.2%} compressed with {self.compression_type})")
            else:
                part_final_data = part_uncompressed_data
                part_final_size = part_uncompressed_size

                self.log(f"\tWriting {part_filename} with size {part_final_size} bytes")

            if part_final_size > self.PART_MAX_SIZE:
                raise Exception(f"The part #{part_index} is too large @ {part_final_size}! Needs to be {self.PART_MAX_SIZE} bytes or less. Try a higher part count if you specified a part count.")

            open(f"{self.out_path}/{part_filename}", "wb").write(part_final_data)

            parts.append(
                UpgradePartMeta(
                    file_name         = part_filename,
                    file_md5          = hashlib.md5(part_final_data).digest(),
                    file_size         = part_final_size,
                    uncompressed_size = part_uncompressed_size,
                    compression_type  = self.compression_type
                )
            )

            blob_start_index = blob_end_index

        return parts

    def obfuscate_part_data(self, part_data):
        for byte_index in range(len(part_data)):
            # Both these operations are done in reverse on the MSNTV2

            # XOR the byte index
            part_data[byte_index] = (part_data[byte_index] ^ byte_index) & 0xff

            # Rotate bits to the right by 3 (handle wrap around with << 5)
            part_data[byte_index] = (part_data[byte_index] >> 3 | part_data[byte_index] << 5) & 0xff

        return part_data

    def generate_package(self):
        self.log(f"Creating file package from files in the '{self.in_path}' directory")

        # A package is a simple array of files:
        #    - First 4 bytes is the size of the entire package (minus 8 to remove for the size and CRC32)
        #    - Next 4 bytes is the CRC32 of the package data with a 0xffffffff starting value.
        #    - The next is the actual package data:
        #        - First 4 bytes is the size of the file.
        #        - Next 12 bytes is the file name. Names this small usually follow a 8.3 format.
        #        - Next bytes are the actual file data, up to the length specified in the first 4 bytes.
        #        ## The next file goes here, following the same file format
        #        ## etc...

        package_blob = bytearray()

        in_path = Path(self.in_path)
        in_files = [file for file in in_path.iterdir() if file.is_file()]
        # The .SIG file needs to be first in the list
        in_files.sort(key=lambda f: f.name not in self.FILEPKG_SIG_FIXES)
        for in_file in in_files:
            upper_file_name = in_file.name.upper()
            file_name = upper_file_name.encode('ascii')
            if len(file_name) > 12:
                file_name = file_name[:12]

            file_data = in_file.read_bytes()

            file_size = len(file_data)

            file_header = struct.pack('<I12s', file_size, file_name.ljust(12, b'\0'))

            self.log(f"\tAdding file '{upper_file_name}' with size {file_size} bytes")

            package_blob.extend(file_header)
            package_blob.extend(file_data)

        package_size = len(package_blob)
        package_crc32 = binascii.crc32(package_blob, 0xffffffff) & 0xffffffff

        if package_size > self.FILEPKG_MAX_SIZE:
            raise Exception(f"The generated package is too large @ {package_size} bytes. It needs to be smaller than {self.FILEPKG_MAX_SIZE} bytes")

        self.log(f"Package created with size {package_size} bytes and CRC32 0x{package_crc32:08x}")

        package_header = struct.pack("<II", package_size, package_crc32)

        return package_header + package_blob

    def generate_part_count(self, final_size):
        part_count = (final_size + self.GEN_PART_MAX_SIZE - 1) // self.GEN_PART_MAX_SIZE

        if part_count > self.MAX_PART_COUNT:
            part_count = self.MAX_PART_COUNT

        return part_count


    def do_fart(self):
        import pygame
        import base64
        import io

        the_intro_base64 = [
            b'''
            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
            +zCwQlE9USLnCSrLYcrw/fsULb419qkkFvOHOX7DXJ6zTsPs/+NYxMRIO8LDGZrJAPfgu7WlSp45
            9lrNHcqUGHZRMupz3qdyzjHOxOk12CZT3CCon/am4Jq6+Ce46lTn1ctSzPO7D+fy+L9w3djevzp6
            f9YVN5boM/rxye/4nlD2vtUP/y3hjhXjVq7Hd6meqaqqzNEYBCtdqSeIYRCezuNKSvnbNn+076vw
            z6BltBdCfT9RmlpaXdmVU1GmkKBZbDsZs3bNLamr8wFwS6/cmi6yLJmpWF1AFoRkeKKFkzxuoagD
            eLxeNlJIl1k0CKLUAC8MEO4oqJEqOlTudHka9nUitBMohOikpJm+PpASRZf8nEsk/+iz/9Emmzq/
            0TiX/mLf/SS/9Fv/opf9aP/zpKogs/UAviVlSHWeTxMHABclTHmTp8Hq0J6L1KOZRwL2mOGG8hq5
            4LczNM8CfEGSHEjHcJlHt/jLIo2oWiQhjpq3bNcB9BzbeHfzyNq3VcROa6w/LOlJ7s2h5IAe/+Mo
            xP4qQ+6zHdhoAJ101bad5KA8OVlzWjtQxRUSILf2AYG+bxEVN7e4deUrfiIr5foHl/9St/0D3/yo
            j/1Qz+qls4CisNz1RnyIaRWaSurAAVC87BTzJwkMAto0oq82eiSt428yoYKIf/MFGNN/Vv//08xW
            0fmKGDDt6blDDllk5S4KCmAuJQ75UjblSHWo/+MoxNgk8+52/HrK0Ep7xKxutRL0kvkvkflmtpli
            PrSqTEFNRTMuMTAwqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqkxBTUUzLjEw
            MKqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqTEFNRTMu
            /+MoxMcVyf4xlDCGmDEwMKqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq
            qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq
            qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq/+MYxMQAAAP8AAAAAKqqqqqqqqqqqqqqqqqq
            qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq/+MYxMQAAANIAAAA
            AKqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq
            qqqq
            ''',
            b'''
            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
            kv////6rXR5yRwKElEiQUWRCuUpStMZvlKWUpZjO/+MoxOImvA6JHnjQuaYz5Sy/mMb/Lyl/0fVD
            PKUsxW5nlNKUrIbMYxqlL/82pS1b/////5jOpSzFvMGG5f8VwpWAIR1prrhENBX0//+j/J620Bqt
            1Yp///9aTEFNRTMuMTAwqqqqqqqqqqqqqqqqqqqqqgk8/ggcJaNxcmXeIFny84v//u////+TTEFN
            RTMu/+MoxMoelAp+PmGEPTEwMKqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq
            UFBR0U0F8b0bFdLVTEFNRTMuMTAwVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
            VVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVVVVVVVVVV/+MYxNIGKBYowGAAAFVVVVVVVVVVVVVV
            VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV/+MYxNsFwBIg
            AFgAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
            VVVVVVVV/+MYxNACyAIooAAAAVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
            VVVVVVVVVVVVVVVVVVVVVVVVVVVV/+MYxMQAAAP8AAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
            VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
            ''',
            b'''
            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
            L4AD/UdLGb1vuH54VtZbpbOLMgCRL9YQGnQPACgMRXEWkkYx/Kt7di9paFwGhM5gKSwA2Nrqm80/
            kYpKS5Wq9exdQoMC8dWH+uk0r1M2JEV4DMJkxnS4+q9Eni2i28bUkZmYo11a3R32dWrbNMy+r6FG
            trOs/f+a+1o1re3tfGM7///9a/////////Fv//8f6390tZujPrxcQ5t4lpv4rvVZP31vresb8GXX
            jPY0FW9mYXF22N71ual5/+NIxMA39A6+/9h4AZ1CzKswTkJiQyE4oeShjfMjatquBAlhwOLQBiYH
            K67pswAAAA37igBe8veaDJRLN97uvny7beBYR5HAYgsULBFSjTwHlaLu2r+5bxFXe5zr7JQhgEgi
            k0635r+/1KFwhB4Tg1QWXr/6u5NrvKQ6UZzVr/5+n+o+7c409Jfvm7uqQo0QhOHIgMaHwmHXXx/V
            V3dRcVLGOnP8vLXUkMudZuOPHPVz8/9RazTfHH//3Mw0w0q1NaqKmr/NWqMuvdJTwPMLKsAACXN4
            VYRWNOtKmcxSzlHMpA/0bRVHRBnTQBGmyqnFjG3XGtXGvVBjIwQ1Jhk0M2scsbkNP9FswICddqvQ
            pBhVUoAgK/qq6rGZqAt1f9Wq/+MoxPMojB6m/MLQiaxm1Y6X9L4aqqrVKNz6THnqrMf//1VzWdVS
            4x7M2pRtjWNM9DGqXWhjUMZN/5SoZ9S5UeZH/QrTSzOjzf//UrGcoUyqCt2IP7fAbQ46wgrpGK87
            gRbWHETbD69ZTlE5AJkNamoRMoiI8dJCLFToltBJT0ZhBiACj1AwUvEQKkyyJYKi/+MoxNMlfBqC
            WtDEvBSZtlFMQU1FMy4xMDBVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVgCgKgrUJQVBXnQVV
            TEFNRTMuMTAwVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
            VVVMQU1FMy4xMDBVVVVVVVVVVVVV/+MYxMALcHpaQHvSBFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
            VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV/+MYxM0EsEo94DJMAVVVVVVVVVVV
            VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV/+MYxNAC
            0A4koBgAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
            VVVVVVVVVVVV/+MYxMQAAAP8AAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
            VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
            '''
        ]

        the_fart_base64 = b'''
        /+NIxAAAAAAAAAAAAFhpbmcAAAAPAAAACQAACCgAMzMzMzMzMzMzMzNcXFxcXFxcXFxcXHBwcHBw
        cHBwcHBwhYWFhYWFhYWFhYWZmZmZmZmZmZmZma6urq6urq6urq6uwsLCwsLCwsLCwsL19fX19fX1
        9fX19f//////////////AAAAPExBTUUzLjEwMAQoAAAAAAAAAAAVCCQEACEAAcwAAAgoeX+b7QAA
        AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
        AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
        AAAA/+NYxAAckXZ4H0wYAAArwAADgfEc/YJANAaEw/OxLBMAcAMCYjn9V69f7BIJkSyJszM38pqx
        zpxhYs6nbf8p2gAAn//u7v7oIRE93RERC64AAIclwQDGDgIAhUD4Pg+8Ew+IDkH+UDEHz4Pv//wQ
        cGPwx8oCAY/yjsTg/lAQBBVoCAAAAtVxpWz5vmoFFAqLghwVxmfj4NbhgGDQSBQPmX/OoaNmWA1E
        yIg2KgeRjIMwRBx0+L0vMQBSvWsJFRCALttu8hkhqyxnyEfJOMkPQexiwakJFnfJpEDeDQbXNUau
        pydggTVBGQKhhKAXU7XI5yVHecrcdJeR1yx3AXN86XZzqM8sro0SnQa0O8JCtQ2FtcRtGuYxtEtV
        LA8UBY10hD8050e2OBcVAc5BieN5ypozFabxyqWrYzq451Yyrg8k20MjIhg68f40qK78BmKMWhYh
        4+EWOfUeUnylUdEYaFc3RarVKPVr/+NIxOhFE8LCWZp4AJLAHxwxEv397qv///gwSEl0EYT66YGw
        u5aq7//v474/FSy6PhthMKhr//9R1YBeJLnAA+Ja5rBhtw+1IAKiwEUYxiljHwWM5lELGqZto2DL
        ZTSo9xY3zbLAu1QqSz7ziDu8+IDypTHTVpAleWL3yhRhVZF597SRykVwv9ccbctMmL9XPFvE3H3X
        aV8VKfKb+/f+iLfcV78VwvIz6pr/hheHl/ur0/+CTHWTf5P4m///////i//9RUHjr/UqgBiQN8AD
        +fudw7UeF2ppVZJaHnQGErDKzM5bSfqllHBPDULE9VTMhTMkXBkVlomdQcSbjt183ztyrdsXm1nj
        MYyzEfR51MNYQ444EGCCuxSsBBh94KCl/+MoxOYji+rc/89AAFqaaSiOzK1ClIx3RbuZCOVFqVjq
        hTVdn2DZjH/+xA9Q7FP/MZP/oqiRLH/5n/9/lt6uTU7oFd7dhyEJBOzqwABKkaSl4AD1roTtpttl
        x03EAMCRfA6JJKOg/HDa/9aHjoi3b3jFjyWZpxC6EqTbkydnpo8kQBToGbsIUyFuaFn/vmCG/+Mo
        xNolFB7ZFsPEVSFi4xq1LnONmsbQDP6WYfZtvi/yCCOHmA8cifQAHewoAhQMJHnoWa4h7xIHfJ2/
        ermGiFwPV2FWbYdqlAJBUbCd4AG/0P3JC7zz2VDMEXnQVKhmEk7IA4MkEhmUy2r43JXJRK4ol6mW
        LLUV+XveefIMex1PcPTq1qxARqAkZPUFCnak/+MoxMgf0hbmXmGGrGwUjk6UL/qrP846//AKlo6Z
        TcMI1vP1nWRjBFKEwVFi4u9S7Cof8OT3/kZKKf+TsQAJcc14AB3e7GSbOt2mnnkvV5GXUjlCfVng
        S3hMz6LmNJBtAngzVntDe49pNvsaiiSFbgwEEHan+zg2FtXHFFWNLQsdlD1zdDPlVXT6hqJbrZHH
        /+MoxMsdwmbiXkmGdKSXWS3UyrE9kFJeZFEh8696X5Ehrd+h/Yz0yERuMWoIgXi6LfPPoiFuWFXe
        W16alDoOAodCgFBgbDUkKVjtnMaFEEkAxAszHBv//9ojO2XKwjR4HBaYcC5j8rf/+mNPPCj6ZYl5
        iRAmqieanqX//yF/m2Z03FzTPZA4kKOI6TKmkoqD/+MoxNcgovLOV08YAGGY////UFkLUmTPw2Fw
        XdMtcjbwg3TNNIjTSiA0kuBoQDQX/////24UWlDk3aR4oHkJixKFgkeEDI0QxEqMFBwQDGAiCD6p
        P//////q0T4y7N4KLOC4eqTSA0yEsMObzBD02I5NNwjN4w48kN86TSpsI6Dc57///////+K0dWXQ
        7BVS/+NYxNdOe3qqWZzYYNx+LTlqUzRkKUZOFmbHZgw+YADGMiBgpMLJRmTGY8imNBhj4InMn7//
        ///////xaNR2Do5K7s/RYzFPlbvZR6nTBXimqCRAGhwcPGFE4EER4IMHDgqDFYCYIJhYDUgWeQnJ
        BUxBTUUzLjEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1F
        My4xMDBVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
        VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
        VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
        VVVVVVVVVVVVVVVVVVVVVVVVVVVV/+MYxMQAAANIAcAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
        VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
        '''
        the_fart = base64.b64decode(the_fart_base64)

        tuned_fart = [
            250,
            random.randrange(10, 500),
            random.randrange(10, 150),
            random.randrange(10, 150),
            random.randrange(10, 150),
            random.randrange(10, 150),
            random.randrange(10, 500)
        ]

        pygame.mixer.init()

        pygame.mixer.music.load(io.BytesIO(base64.b64decode(random.choice(the_intro_base64))))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)

        pygame.mixer.music.load(io.BytesIO(the_fart)) 
        for delay in tuned_fart:
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)

            time.sleep(delay / 1000)
            pygame.mixer.music.rewind()
        
        pygame.mixer.music.stop()

if __name__ == "__main__":
    Msntv2GenDr()
