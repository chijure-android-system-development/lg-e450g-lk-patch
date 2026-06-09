#!/usr/bin/env python3
"""
validate_and_patch_uboot.py
Parche v7 para LG E450g LK bootloader (MT6575)

NOPs 8 ramas de error en 4 rutas + fuerza R0=0 en verificador post-carga:
  P1 (boot path)        0x181EC: BLT.W → NOP NOP  (tras BL 0x01E01A18)
  P2 (boot path)        0x18204: BLT.W → NOP NOP  (tras BL 0x01E020D4)
  P3 (path A)           0x18342: BLT.W → NOP NOP  (tras BL 0x01E01CFC)
  P4 (path A)           0x18358: BLT.W → NOP NOP  (tras BL 0x01E021F0)
  P5 (path B)           0x18382: BLT.W → NOP NOP  (tras BL 0x01E01F9C)
  P6 (path B)           0x18396: BLT.W → NOP NOP  (tras BL 0x01E0230C)
  P7 (recovery path C)  0x18556: BLT.N → NOP      (tras BL 0x01E01A18)
  P8 (recovery path C)  0x1856A: BGE.W → B.W      (fuerza exito, same target)
  P9 (post-load verify) 0x184E2: BL 0x01E1EEB0 → MOVS R0,#0; NOP
"""

import sys
import hashlib

SHA256_ORIG = "d35f0bbf245298a0bcc5d4427b73c293273be2de1777fb3bc669d6a4d963215a"
SHA256_V7   = "973e0ed498917d3ec86dc10d3e1c53357980dfd4df43ced09aa51c644df7e99a"

PATCHES = [
    (0x181EC, b'\xC0\xF2\xEC\x81', b'\x00\xBF\x00\xBF', "P1 boot  BLT.W→NOP tras BL 0x01E01A18"),
    (0x18204, b'\xC0\xF2\xE5\x81', b'\x00\xBF\x00\xBF', "P2 boot  BLT.W→NOP tras BL 0x01E020D4"),
    (0x18342, b'\xC0\xF2\x3C\x81', b'\x00\xBF\x00\xBF', "P3 pathA BLT.W→NOP tras BL 0x01E01CFC"),
    (0x18358, b'\xC0\xF2\x2C\x81', b'\x00\xBF\x00\xBF', "P4 pathA BLT.W→NOP tras BL 0x01E021F0"),
    (0x18382, b'\xC0\xF2\xDB\x80', b'\x00\xBF\x00\xBF', "P5 pathB BLT.W→NOP tras BL 0x01E01F9C"),
    (0x18396, b'\xC0\xF2\x21\x81', b'\x00\xBF\x00\xBF', "P6 pathB BLT.W→NOP tras BL 0x01E0230C"),
    (0x18556, b'\x46\xDB',         b'\x00\xBF',         "P7 recov BLT.N→NOP tras BL 0x01E01A18"),
    (0x1856A, b'\xBF\xF6\x16\xAF', b'\xFF\xF7\x16\xBF', "P8 recov BGE.W→B.W fuerza exito"),
    (0x184E2, b'\x06\xF0\xE5\xFD', b'\x00\x20\x00\xBF', "P9 loadpath BL 0x01E1EEB0→MOVS R0,#0;NOP"),
]

def main():
    if len(sys.argv) < 2:
        print(f"Uso: {sys.argv[0]} uboot_orig.bin [uboot_patched_v7.bin]")
        sys.exit(1)

    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else "uboot_patched_v7.bin"

    print(f"[*] Leyendo {src}")
    with open(src, 'rb') as f:
        orig = f.read()

    if len(orig) != 524288:
        print(f"[!] Tamaño incorrecto: {len(orig)} (esperado 524288)")
        sys.exit(1)
    print(f"    Tamaño: {len(orig)} bytes  OK")

    sha = hashlib.sha256(orig).hexdigest()
    if sha != SHA256_ORIG:
        print(f"[!] SHA256 no coincide con original conocido")
        print(f"    Esperado: {SHA256_ORIG}")
        print(f"    Obtenido: {sha}")
        sys.exit(1)
    print(f"    SHA256 original verificado  OK")

    data = bytearray(orig)

    print()
    print("[*] Aplicando parches:")
    for off, old_b, new_b, desc in PATCHES:
        actual = bytes(data[off:off+len(old_b)])
        if actual != old_b:
            print(f"[!] {desc}: bytes en 0x{off:05X} no coinciden")
            print(f"    Esperado: {old_b.hex()}")
            print(f"    Obtenido: {actual.hex()}")
            sys.exit(1)
        data[off:off+len(old_b)] = new_b
        print(f"    0x{off:05X}: {old_b.hex()} → {new_b.hex()}  ({desc})")

    sha_out = hashlib.sha256(bytes(data)).hexdigest()
    print()
    print(f"[*] SHA256 parcheado: {sha_out}")
    if sha_out != SHA256_V7:
        print(f"[!] SHA256 no coincide con v7 esperado ({SHA256_V7})")
        sys.exit(1)
    print(f"    SHA256 v7 verificado  OK")

    with open(dst, 'wb') as f:
        f.write(data)
    print(f"[+] Escrito: {dst} ({len(data)} bytes)")

if __name__ == "__main__":
    main()
