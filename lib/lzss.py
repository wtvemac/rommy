import ctypes

class lzss():
    context = {
        "ring_buffer_size": 0x1000,
        "root_index": 0x1000,
        "max_match_length": 0x12,#0x11,
        "match_threshold": 0x03,
        "match_position": 0x00,
        "match_length": 0x00,
        "ring_buffer": [],
        "parent": [],
        "lchild": [],
        "rchild": [],
    }

    def __init__(self):
        self.clear()

    def clear(self):
        self.context["match_position"] = 0x00
        self.context["match_length"] = 0x00
        self.context["ring_buffer"] = bytearray(self.context["ring_buffer_size"] + self.context["max_match_length"])
        self.context["parent"] = [0x00000000] * (self.context["ring_buffer_size"] + 0x01)
        self.context["rchild"] = [0x00000000] * ((self.context["ring_buffer_size"] * 2) + 0x01) 
        self.context["lchild"] = [0x00000000] * ((self.context["ring_buffer_size"] * 2) + 0x01)

        for ii in range(self.context["ring_buffer_size"] - self.context["max_match_length"]):
            self.context["ring_buffer"][ii] = 0x20

        for ii in range(self.context["ring_buffer_size"] + 1, len(self.context["rchild"])):
            self.context["rchild"][ii] = self.context["root_index"]

        for ii in range(self.context["ring_buffer_size"] - 1):
            self.context["parent"][ii] = self.context["root_index"]

    def InsertNode(self, i):
        keyi = self.context["ring_buffer"][i]
        keyii = self.context["ring_buffer"][i + 1] ^ self.context["ring_buffer"][i + 2]
        keyii = ((keyii ^ (keyii >> 4)) & 0x0F) << 8

        parent_index = i
        parent_link =  (self.context["root_index"] + 1) + keyi + keyii
        child_index = parent_link
        child_link = i

        self.context["rchild"][i] = self.context["root_index"]
        self.context["lchild"][i] = self.context["root_index"]
        self.context["match_length"] = 0x00

        matched_list = self.context["rchild"]
        cmp_index = 1
        looped = 0
        while True:
            looped += 1

            if looped >= 0xFFFF:
                raise Exception('Runaway loop')

            if cmp_index >= 0:
                cmp_index = self.context["rchild"][parent_link]
                matched_list = self.context["rchild"]
            else:
                cmp_index = self.context["lchild"][parent_link]
                matched_list = self.context["lchild"]

            if cmp_index == self.context["root_index"]:
                parent_index = i
                child_index = parent_link
                child_link = i
                break

            parent_link = cmp_index
            ii = 1
            while ii < self.context["max_match_length"]:
                if self.context["ring_buffer"][i + ii] != self.context["ring_buffer"][parent_link + ii]:
                    break

                ii += 1

            if ii > self.context["match_length"]:
                self.context["match_length"] = ii
                self.context["match_position"] = parent_link

                if ii > (self.context["max_match_length"] - 1):
                    self.context["parent"][i] = self.context["parent"][parent_link]

                    self.context["rchild"][i] = self.context["rchild"][parent_link]
                    self.context["lchild"][i] = self.context["lchild"][parent_link]

                    self.context["parent"][self.context["rchild"][i]] = i
                    self.context["parent"][self.context["lchild"][i]] = i

                    if self.context["rchild"][self.context["parent"][parent_link]] != parent_link:
                        matched_list = self.context["lchild"]
                    else:
                        matched_list = self.context["rchild"]

                    child_index = self.context["parent"][parent_link]
                    child_link = i
                    parent_index = parent_link
                    parent_link = self.context["root_index"]
                    break

        self.context["parent"][parent_index] = parent_link

        matched_list[child_index] = child_link

    def DeleteNode(self, i):
        if self.context["parent"][i] != self.context["root_index"]:
            ii = 0
            if self.context["rchild"][i] == self.context["root_index"]:
                ii = self.context["lchild"][i]
            elif self.context["lchild"][i] == self.context["root_index"]:
                ii = self.context["rchild"][i]
            else:
                ii = self.context["lchild"][i]

                if ii != self.context["root_index"]:
                    looped = 0
                    while ii != self.context["root_index"]:
                        looped += 1
                        if looped >= 0xFFFF:
                            raise Exception('Runaway loop')

                        ii = self.context["rchild"][ii]
                    

                    self.context["rchild"][self.context["parent"][ii]] = self.context["lchild"][ii]
                    self.context["parent"][self.context["lchild"][ii]] = self.context["parent"][ii]

                    self.context["lchild"][ii] = self.context["lchild"][i]
                    self.context["parent"][self.context["lchild"][i]] = ii

                self.context["rchild"][ii] = self.context["rchild"][i]
                self.context["parent"][self.context["rchild"][i]] = ii

            self.context["parent"][ii] = self.context["parent"][i]

            parent_link = self.context["parent"][i]
            if self.context["rchild"][parent_link] != i:
                self.context["lchild"][parent_link] = ii
            else:
                self.context["rchild"][parent_link] = ii

            self.context["parent"][i] = self.context["root_index"]

    def Lzss_Compress(self, uncompressed_data):
        uncompressed_size = len(uncompressed_data)
        i = 0
        ring_index = 0
        ring_footer_start = self.context["root_index"] - self.context["max_match_length"] - 1
        footer_index = ring_footer_start

        length = 0
        while length <= self.context["max_match_length"] and i < uncompressed_size:
            self.context["ring_buffer"][ring_footer_start + length] = uncompressed_data[i]

            i += 1
            length += 1

        mask = 1
        code_buffer = bytearray(0x14)
        code_buffer_index = 1

        compressed_data = bytearray()

        self.InsertNode(ring_footer_start)
        while length > 0:
            if self.context["match_length"] > length:
                self.context["match_length"] = length
            
            if self.context["match_length"] >= self.context["match_threshold"]:
                _match_position = footer_index - self.context["match_position"] - 1
                if _match_position < 0:
                    _match_position += self.context["root_index"]

                code_buffer[code_buffer_index] = _match_position & 0xFF
                code_buffer_index += 1

                code_buffer[code_buffer_index] = (((_match_position >> 4) & 0xF0) | (self.context["match_length"] - self.context["match_threshold"])) & 0xFF
                code_buffer_index += 1
            else:
                self.context["match_length"] = 1
                code_buffer[0] = (code_buffer[0] | mask) & 0xFF
                code_buffer[code_buffer_index] = self.context["ring_buffer"][footer_index] & 0xFF
                code_buffer_index += 1

            mask <<= 1
            mask &= 0xFF

            if mask == 0:
                for ii in range(code_buffer_index):
                    compressed_data.append(code_buffer[ii])

                code_buffer[0] = 0
                mask = 1
                code_buffer_index = 1


            last_match_length = self.context["match_length"]
            if last_match_length > 0:
                ii = 0
                while ii < last_match_length:
                    self.DeleteNode(ring_index)

                    if i < uncompressed_size:
                        self.context["ring_buffer"][ring_index] = uncompressed_data[i]

                        if ring_index <= (self.context["max_match_length"] - 1):
                            self.context["ring_buffer"][self.context["ring_buffer_size"] + ring_index] = uncompressed_data[i]
                    else:
                        i = (uncompressed_size - 1)
                        length -= 1

                    ring_index = (ring_index + 1) & (self.context["ring_buffer_size"] - 1)
                    footer_index = (footer_index + 1) & (self.context["ring_buffer_size"] - 1)

                    if length != 0:
                        self.InsertNode(footer_index)

                    i += 1
                    ii += 1

        if code_buffer_index > 1:
            for ii in range(code_buffer_index):
                compressed_data.append(code_buffer[ii])
        
        return compressed_data
            
    def Lzss_Expand(self, compressed_data, uncompressed_size = 0, flags_start = 0x0000):
        compressed_size = len(compressed_data)

        if uncompressed_size == 0:
            uncompressed_size = compressed_size * 4

        uncompressed_data = bytearray(uncompressed_size + 0x100)

        flags = flags_start
        i = 0
        r = 0

        def _add_byte(byte):
            nonlocal r
            uncompressed_data[r] = byte
            r += 1

        while i < compressed_size:
            if (flags & 0x100) == 0:
                flags = ctypes.c_uint32(compressed_data[i]).value | 0xFF00
                i += 1

            byte = ctypes.c_uint32(compressed_data[i]).value
            if (flags & 0x01) == 0x01:
                _add_byte(byte)
            else:
                i += 1
                next_byte = ctypes.c_uint32(compressed_data[i]).value

                m = ((next_byte & 0xF0) << 4) | byte

                for ii in range((next_byte & 0x0F) + self.context["match_threshold"]):
                    _add_byte(uncompressed_data[r - (m + 1)])

            flags >>= 1
            i += 1

            if r >= uncompressed_size:
                break

        return uncompressed_data[0:r]