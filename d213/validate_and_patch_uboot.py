#!/usr/bin/env python3
"""
Parche verificado para LG D213 (L50) LK bootloader (MT6572), firmware LGD213AT V10f.

Origen: parche compartido en 4pda.ru (usuario alekcacko), YA verificado en
hardware real por un tercero (TWRP arranca sin "Security Error"). Comparado
byte a byte contra el dump propio del dispositivo (uboot_raw.bin) -- son
identicos salvo estos 2 parches, confirmando que es exactamente el mismo
build de firmware, no solo "el mismo modelo".

  P1 (file 0x19B5A): BLT.W 0x19E3C -> MOVS R0,#0 (x2)
     Rama de error del dispatcher de verificacion (mismo bloque de codigo
     identificado por analisis estructural propio en ANALYSIS.md, aunque el
     branch exacto no se habia mapeado ahi).
  P2 (file 0x2CFBC): MOV R4,R0; CBNZ R0,error(retorna -1)
                      -> MOVS R4,#0; MOVS R0,#0
     Verificacion post-lectura (probable verificacion de certificado) en una
     funcion distinta -- fuerza R0=0/R4=0 y elimina el salto a error.
"""

import sys
import hashlib

SHA256_ORIG = "d5f9c078bab3ea3c0561c9153151132b886b422ced718e762979f7b5a4653045"
SHA256_PATCHED_EXPECTED = "c6b7b8b327373462d6ec0b401f6c197b9b366411d5c8fbb542e3c199614607d6"

PATCHES = [
    (0x19B5A, bytes.fromhex('c0f26f81'), bytes.fromhex('00200020'),
     "P1: BLT.W 0x19E3C -> MOVS R0,#0 x2"),
    (0x2CFBC, bytes.fromhex('044678b9'), bytes.fromhex('00240020'),
     "P2: MOV R4,R0;CBNZ R0,error -> MOVS R4,#0;MOVS R0,#0"),
]

def main():
    if len(sys.argv) < 2:
        print(f"Uso: {sys.argv[0]} uboot_raw.bin [uboot_patched.bin]")
        sys.exit(1)

    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else "uboot_patched.bin"

    with open(src, 'rb') as f:
        orig = f.read()

    if len(orig) != 524288:
        print(f"[!] Tamano incorrecto: {len(orig)} (esperado 524288)")
        sys.exit(1)

    sha = hashlib.sha256(orig).hexdigest()
    if sha != SHA256_ORIG:
        print(f"[!] SHA256 no coincide con el original conocido (LGD213AT V10f)")
        print(f"    Esperado: {SHA256_ORIG}")
        print(f"    Obtenido: {sha}")
        sys.exit(1)
    print("[*] SHA256 original verificado OK (LGD213AT V10f)")

    data = bytearray(orig)
    for off, old_b, new_b, desc in PATCHES:
        actual = bytes(data[off:off + len(old_b)])
        if actual != old_b:
            print(f"[!] {desc}: bytes en 0x{off:05X} no coinciden")
            print(f"    Esperado: {old_b.hex()}  Obtenido: {actual.hex()}")
            sys.exit(1)
        data[off:off + len(old_b)] = new_b
        print(f"    0x{off:05X}: {old_b.hex()} -> {new_b.hex()}  ({desc})")

    sha_out = hashlib.sha256(bytes(data)).hexdigest()
    if sha_out != SHA256_PATCHED_EXPECTED:
        print(f"[!] SHA256 de salida no coincide con el parche verificado de 4pda")
        print(f"    Esperado: {SHA256_PATCHED_EXPECTED}")
        print(f"    Obtenido: {sha_out}")
        sys.exit(1)
    print(f"[*] SHA256 parcheado: {sha_out}  (coincide con el parche verificado de 4pda)")

    with open(dst, 'wb') as f:
        f.write(data)
    print(f"[+] Escrito: {dst} ({len(data)} bytes)")

if __name__ == "__main__":
    main()
