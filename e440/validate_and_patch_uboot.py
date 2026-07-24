#!/usr/bin/env python3
"""
validate_and_patch_uboot.py
Parche v1 para LG E440g LK bootloader (MT6575)

Derivado del mismo análisis que e450/investicagion_bootloader (misma función de
verificación, misma familia MT6575/Android 4.1.2), pero recompilado en una
dirección distinta (delta ~0x2030 respecto al binario del E450 en la zona de
entrada; los offsets exactos se re-derivaron con desensamblado propio, no se
asumió el delta constante para toda la función).

NOPs 6 ramas BLT.W/BLT.N + fuerza B.W incondicional en 1 rama BGE.W + fuerza
R0=0 en el verificador post-carga:
  P1 (boot path)        0x161BC: BLT.W → NOP NOP  (tras BL verify_image1)
  P2 (boot path)        0x161D4: BLT.W → NOP NOP  (tras BL verify_image2)
  P3 (path A)           0x1633A: BLT.W → NOP NOP  (tras BL pathA_func1)
  P4 (path A)           0x16350: BLT.W → NOP NOP  (tras BL pathA_func2)
  P5 (path B)           0x1637A: BLT.W → NOP NOP  (tras BL pathB_func1)
  P6 (path B)           0x1638E: BLT.W → NOP NOP  (tras BL pathB_func2)
  P7 (recovery path C)  0x16562: BLT.N → NOP      (tras BL verify_image1, 3ra vez)
  P8 (recovery path C)  0x16576: BGE.W → B.W      (fuerza éxito, mismo target)
  P9 (post-load verify) 0x164E2: BL postload_verify → MOVS R0,#0; NOP

Ver ANALYSIS.md en este mismo directorio para el desensamblado completo y la
verificación cruzada contra el análisis del E450.
"""

import sys
import hashlib

SHA256_ORIG = "79c7148274a19e1159a302462d0b7ee4ffbd5d764e8a8ca012aa59057b62251c"

PATCHES = [
    (0x161BC, b'\xC0\xF2\x0A\x82', b'\x00\xBF\x00\xBF', "P1 boot  BLT.W→NOP tras BL verify_image1"),
    (0x161D4, b'\xC0\xF2\x03\x82', b'\x00\xBF\x00\xBF', "P2 boot  BLT.W→NOP tras BL verify_image2"),
    (0x1633A, b'\xC0\xF2\x46\x81', b'\x00\xBF\x00\xBF', "P3 pathA BLT.W→NOP tras BL pathA_func1"),
    (0x16350, b'\xC0\xF2\x36\x81', b'\x00\xBF\x00\xBF', "P4 pathA BLT.W→NOP tras BL pathA_func2"),
    (0x1637A, b'\xC0\xF2\xE5\x80', b'\x00\xBF\x00\xBF', "P5 pathB BLT.W→NOP tras BL pathB_func1"),
    (0x1638E, b'\xC0\xF2\x2B\x81', b'\x00\xBF\x00\xBF', "P6 pathB BLT.W→NOP tras BL pathB_func2"),
    (0x16562, b'\x46\xDB',         b'\x00\xBF',         "P7 recov BLT.N→NOP tras BL verify_image1 (3ra vez)"),
    (0x16576, b'\xBF\xF6\x0C\xAF', b'\xFF\xF7\x0C\xBF', "P8 recov BGE.W→B.W fuerza exito (mismo target 0x01E16192)"),
    (0x164E2, b'\x06\xF0\x57\xFC', b'\x00\x20\x00\xBF', "P9 loadpath BL postload_verify→MOVS R0,#0;NOP"),
]

def main():
    if len(sys.argv) < 2:
        print(f"Uso: {sys.argv[0]} uboot_raw.bin [uboot_patched_v1.bin]")
        sys.exit(1)

    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else "uboot_patched_v1.bin"

    print(f"[*] Leyendo {src}")
    with open(src, 'rb') as f:
        orig = f.read()

    if len(orig) != 524288:
        print(f"[!] Tamaño incorrecto: {len(orig)} (esperado 524288)")
        sys.exit(1)
    print(f"    Tamaño: {len(orig)} bytes  OK")

    sha = hashlib.sha256(orig).hexdigest()
    if sha != SHA256_ORIG:
        print(f"[!] SHA256 no coincide con el original conocido del E440")
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

    with open(dst, 'wb') as f:
        f.write(data)
    print(f"[+] Escrito: {dst} ({len(data)} bytes)")

if __name__ == "__main__":
    main()
