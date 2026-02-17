import binascii
import apsw
import struct
import os
import UnityPy

class UmaCrypto:
    def __init__(self, config):
        self.cfg = config

    def get_meta_connection(self):
        """Returns a connection to the encrypted 'meta' database."""
        base_key = binascii.unhexlify(self.cfg['DB_BASE_KEY_HEX'])
        raw_key = binascii.unhexlify(self.cfg['DB_KEY_JP_HEX'])
        key_list = list(raw_key)
        
        # XOR Key Generation
        for i in range(len(key_list)):
            key_list[i] ^= base_key[i % 13]
        
        final_key_hex = binascii.hexlify(bytes(key_list)).decode('utf-8')
        
        if not os.path.exists(self.cfg['PATHS']['meta']):
            raise FileNotFoundError(f"Meta file not found at {self.cfg['PATHS']['meta']}")

        conn = apsw.Connection(self.cfg['PATHS']['meta'])
        cursor = conn.cursor()
        cursor.execute("PRAGMA cipher='chacha20'")
        cursor.execute(f"PRAGMA hexkey='{final_key_hex}'")
        cursor.execute("PRAGMA cipher_use_hmac=OFF")
        return conn

    def decrypt_asset(self, item_dict):
        """
        Decrypts a Unity asset (timeline, lipsync, ruby) based on its manifest key.
        Returns a UnityPy environment object.
        """
        file_path = item_dict['path']
        file_key = item_dict['encryption_key']
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Asset file missing: {file_path}")

        with open(file_path, "rb") as f:
            data = bytearray(f.read())

        # If key is 0, file is not encrypted (common for audio, rare for assets)
        if file_key == 0:
            return UnityPy.load(bytes(data))

        # XOR Decryption Logic for Assets
        base_keys = bytes.fromhex(self.cfg['AB_KEY_HEX'])
        key_bytes = struct.pack('<q', file_key)
        
        # Prepare the rolling XOR key
        f_key = bytearray(len(base_keys) * 8)
        for i in range(len(base_keys)):
            for j in range(8):
                f_key[(i << 3) + j] = base_keys[i] ^ key_bytes[j]

        # Decrypt payload (skipping the 256-byte header)
        f_key_len = len(f_key)
        header_size = self.cfg['HEADER_SIZE']
        
        if len(data) > header_size:
            for i in range(header_size, len(data)):
                data[i] ^= f_key[i % f_key_len]
        
        return UnityPy.load(bytes(data))