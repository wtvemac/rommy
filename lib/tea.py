import ctypes

class tea():
    def encrypt(data, key):
        _key = [
            int.from_bytes(key[0:4], "little"),
            int.from_bytes(key[4:8], "little"),
            int.from_bytes(key[8:12], "little"),
            int.from_bytes(key[12:16], "little")
        ]

        _data = [
            ctypes.c_uint32(int.from_bytes(data[0:4], "little")),
            ctypes.c_uint32(int.from_bytes(data[4:8], "little"))
        ]

        sum   = ctypes.c_uint32(0)
        delta = ctypes.c_uint32(0x9E3779B9)

        for i in range(32):
            sum.value += delta.value
            
            _data[0].value += ( _data[1].value << 4 ) + _key[0] ^ _data[1].value + sum.value ^ ( _data[1].value >> 5 ) + _key[1]
            _data[1].value += ( _data[0].value << 4 ) + _key[2] ^ _data[0].value + sum.value ^ ( _data[0].value >> 5 ) + _key[3]

        return (_data[0].value.to_bytes(4, "little") + _data[1].value.to_bytes(4, "little"))

    def decrypt(data, key):
        _key = [
            int.from_bytes(key[0:4], "little"),
            int.from_bytes(key[4:8], "little"),
            int.from_bytes(key[8:12], "little"),
            int.from_bytes(key[12:16], "little")
        ]

        _data = [
            ctypes.c_uint32(int.from_bytes(data[0:4], "little")),
            ctypes.c_uint32(int.from_bytes(data[4:8], "little"))
        ]

        sum   = ctypes.c_uint32(0xC6EF3720)
        delta = ctypes.c_uint32(0x9E3779B9)

        for i in range(32):
            _data[1].value -= ( _data[0].value << 4 ) + _key[2] ^ _data[0].value + sum.value ^ ( _data[0].value >> 5 ) + _key[3]
            _data[0].value -= ( _data[1].value << 4 ) + _key[0] ^ _data[1].value + sum.value ^ ( _data[1].value >> 5 ) + _key[1]

            sum.value -= delta.value

        return (_data[0].value.to_bytes(4, "little") + _data[1].value.to_bytes(4, "little"))