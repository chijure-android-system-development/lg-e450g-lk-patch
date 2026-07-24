# LG E440g (MT6575) LK Bootloader Patch — Unsigned Recovery Boot

Investigación y parche para el bootloader LK del **LG Optimus L4 II (E440g)**
que permite bootear recoveries no firmados (CWM, TWRP) sin "Security Error",
sin romper el boot de la ROM stock. Deriva directamente de la metodología ya
verificada en hardware para el [LG E450g](../README.md)
(mismo SoC MT6575, mismo Android 4.1.2): la función de verificación de firma
es la **misma**, recompilada en otra dirección — se re-encontraron todos los
offsets con desensamblado propio y verificación cruzada byte a byte contra el
binario del E450 (ver `ANALYSIS.md`).

**Estado (2026-07-23): parche flasheado y verificado en el dispositivo real, objetivo completo.**
`uboot_patched_v1.bin` fue escrito en `/dev/uboot`, el readback coincide por
SHA256, y tras reboot el dispositivo volvió a arrancar la ROM stock con
normalidad (ADB reconectó, root sigue funcionando, uptime fresco de reboot).
Además, un recovery TWRP no firmado fue probado y **arranca correctamente**
(sin "Security Error") — confirma el bypass funcionando de punta a punta.

---

## Hardware confirmado (en el dispositivo real, 2026-07-22)

| Campo | Valor |
|---|---|
| Modelo | `LG-E440g` (`ro.product.model`) |
| Android | 4.1.2 |
| SoC | MediaTek MT6575 |
| Root | Obtenido por el usuario antes de esta sesión (uid=0 confirmado vía `adb shell su -c id`) |

## Tabla de particiones (E440, vía `/proc/dumchar_info`)

```
uboot        0x0000000000080000   0x0000000001180000   2   /dev/block/mmcblk0
```

Misma `StartAddr` (`0x1180000`) y mismo tamaño (`0x80000` = 524288 bytes) que
el E450 — el layout de partición eMMC es idéntico. En el E440 además existe
el device node `/dev/uboot` (`crw------- root root 237,10`), por lo que se
puede volcar directamente con `dd if=/dev/uboot` sin calcular `seek` sobre
`mmcblk0`.

## Backups originales

Guardados localmente (fuera de este repositorio, son binarios propietarios)
**antes** de cualquier modificación:

| Archivo | Tamaño | SHA256 |
|---|---|---|
| `uboot_raw.bin` | 524288 | `79c7148274a19e1159a302462d0b7ee4ffbd5d764e8a8ca012aa59057b62251c` |
| `boot_raw.img` | 8388608 | ver `SHA256SUMS.txt` |
| `recovery_raw.img` | 7340032 | ver `SHA256SUMS.txt` |

## Cómo se encontraron los offsets (resumen — ver `ANALYSIS.md` para el detalle)

1. Se confirmó que el binario del E440 comparte el mismo formato de cabecera
   `LK` y el mismo mapeo `VMA = file_offset + 0x01E00000 - 0x200` que el E450
   (ambos usan MT6575 + mismo toolchain de MediaTek).
2. Se extrajeron firmas de bytes (8-16 bytes) de las funciones clave del
   E450 (`check_security`, `verify_image1/2`, rutas A/B, verificador
   post-carga) y se buscaron en el binario del E440 — **todas** aparecieron
   como coincidencia exacta y única, en offsets distintos (delta no
   constante entre funciones, indicando recompilación real, no solo
   relocación).
3. Con esos anclajes, se desensambló la función `check_security` completa
   del E440 (mismo desensamblador Thumb-2 usado en `e450/analyze_bootloader.py`)
   y se identificaron las 9 ramas de error/éxito equivalentes a los 9 parches
   del E450, en la misma posición relativa dentro de la misma estructura de
   4 rutas (boot, path A, path B, path C/recovery) + verificador post-carga.
4. Para el parche P8 (BGE.W → B.W incondicional, mismo target), se escribió
   un codificador T4 de Thumb-2 y se **validó contra el propio parche v7 del
   E450 verificado en hardware** (bytes conocidos `BF F6 16 AF` → `FF F7 16 BF`)
   antes de aplicarlo al caso del E440 — el codificador reproduce exactamente
   los bytes ya probados en el E450, dando confianza en la técnica antes de
   generar los bytes nuevos para el E440.

## Los 9 parches (v1, verificado en hardware)

| Parche | File offset | Bytes originales | Bytes nuevos | Descripción |
|---|---|---|---|---|
| P1 | `0x161BC` | `C0 F2 0A 82` | `00 BF 00 BF` | NOP BLT.W — boot path, tras BL verify_image1 |
| P2 | `0x161D4` | `C0 F2 03 82` | `00 BF 00 BF` | NOP BLT.W — boot path, tras BL verify_image2 |
| P3 | `0x1633A` | `C0 F2 46 81` | `00 BF 00 BF` | NOP BLT.W — path A, tras BL pathA_func1 |
| P4 | `0x16350` | `C0 F2 36 81` | `00 BF 00 BF` | NOP BLT.W — path A, tras BL pathA_func2 |
| P5 | `0x1637A` | `C0 F2 E5 80` | `00 BF 00 BF` | NOP BLT.W — path B, tras BL pathB_func1 |
| P6 | `0x1638E` | `C0 F2 2B 81` | `00 BF 00 BF` | NOP BLT.W — path B, tras BL pathB_func2 |
| P7 | `0x16562` | `46 DB` | `00 BF` | NOP BLT.N — recovery path C, tras BL verify_image1 (3ra vez) |
| P8 | `0x16576` | `BF F6 0C AF` | `FF F7 0C BF` | BGE.W → B.W — recovery path C, fuerza éxito (mismo target `0x01E16192`) |
| P9 | `0x164E2` | `06 F0 57 FC` | `00 20 00 BF` | BL postload_verify → MOVS R0,#0; NOP — verificación post-lectura |

SHA256 original:   `79c7148274a19e1159a302462d0b7ee4ffbd5d764e8a8ca012aa59057b62251c`
SHA256 parcheado (`uboot_patched_v1.bin`): `49427f704d95b09fac8b172e5d18cb83cdb26c612b578ffee364c5a8acee0c79`

## Regenerar el parche

```bash
python3 validate_and_patch_uboot.py ../backups-originales/uboot_raw.bin uboot_patched_v1.bin
```

## Pendiente

- [x] Confirmación explícita del usuario para escribir en la partición `uboot` real — obtenida.
- [x] Flasheo y verificación de readback SHA256 — hecho, coincide.
- [x] Confirmar que la ROM stock sigue arrancando con normalidad tras el parche — confirmado (reboot, ADB reconectó, root funcional).
- [x] Conseguir un recovery no firmado (TWRP) para el E440 y confirmar que arranca sin "Security Error" — confirmado, objetivo del parche cumplido.
- [ ] Opcional: verificar que mtkclient (`/media/chijure/Datos/Descargas/mtkclient`) reconoce el E440 en modo Preloader, como vía adicional de recuperación por USB para el futuro (ya no es urgente dado que el reboot post-parche fue exitoso).

## Flashear vía ADB (root ya obtenido)

```bash
# Backup ya hecho (ver ../backups-originales/), pero re-verificar antes de escribir:
adb shell "su -c 'dd if=/dev/uboot of=/data/local/tmp/uboot_bak_check.bin bs=4096 count=128'"
adb pull /data/local/tmp/uboot_bak_check.bin /tmp/uboot_bak_check.bin
sha256sum /tmp/uboot_bak_check.bin   # debe coincidir con 79c7148274a19e1159a302462d0b7ee4ffbd5d764e8a8ca012aa59057b62251c

# Flash
adb push uboot_patched_v1.bin /data/local/tmp/uboot_v1.bin
adb shell "su -c 'dd if=/data/local/tmp/uboot_v1.bin of=/dev/uboot bs=4096 count=128 && sync'"
adb shell "su -c 'rm /data/local/tmp/uboot_v1.bin /data/local/tmp/uboot_bak_check.bin'"

# Verificar (SHA256 debe coincidir con uboot_patched_v1.bin)
adb shell "su -c 'dd if=/dev/uboot of=/data/local/tmp/rb.bin bs=4096 count=128'"
adb pull /data/local/tmp/rb.bin && sha256sum rb.bin
```
