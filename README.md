# LG E450g (MT6575) LK Bootloader Patch — Unsigned Recovery Boot

Investigación y parche para el bootloader LK del **LG Optimus L5 II (E450g)** que permite bootear recoveries no firmados (CWM, TWRP) sin "Security Error", sin romper el boot de la ROM stock.

**Resultado:** 9 parches en el binario `uboot_orig.bin` (v7) — verificado en hardware. CWM 6.0.4.4 arranca correctamente.

---

## Inicio rápido

```bash
# Requiere uboot_orig.bin (obtener de tu dispositivo con dd o Octoplus/SP Flash Tool)
python3 validate_and_patch_uboot.py uboot_orig.bin uboot_patched_v7.bin

# SHA256 esperados:
# uboot_orig.bin       d35f0bbf245298a0bcc5d4427b73c293273be2de1777fb3bc669d6a4d963215a
# uboot_patched_v7.bin 973e0ed498917d3ec86dc10d3e1c53357980dfd4df43ced09aa51c644df7e99a
```

### Flashear vía ADB (root requerido)

```bash
# Backup primero
adb shell "su -c 'dd if=/dev/block/mmcblk0 bs=512 skip=35840 count=1024 of=/data/local/tmp/uboot_bak.bin && chmod 644 /data/local/tmp/uboot_bak.bin'"
adb pull /data/local/tmp/uboot_bak.bin uboot_backup.bin

# Flash
adb push uboot_patched_v7.bin /data/local/tmp/uboot_v7.bin
adb shell "su -c 'dd if=/data/local/tmp/uboot_v7.bin of=/dev/block/mmcblk0 bs=512 seek=35840 && sync'"
adb shell "su -c 'rm /data/local/tmp/uboot_v7.bin'"

# Verificar (SHA256 debe coincidir con uboot_patched_v7.bin)
adb shell "su -c 'dd if=/dev/block/mmcblk0 bs=512 skip=35840 count=1024 of=/data/local/tmp/rb.bin && chmod 644 /data/local/tmp/rb.bin'"
adb pull /data/local/tmp/rb.bin && sha256sum rb.bin

# Probar recovery
adb reboot recovery
```

---

## Hardware

| Campo | Valor |
|---|---|
| Dispositivo | LG Optimus L5 II (E450g) |
| SoC | MediaTek MT6575 |
| Android | 4.1.2 |
| USB VID:PID | `1004:61f1` ("MediaTek MT65xx Preloader") |
| HW code | `0x6575` |
| HW subcode | `0x8a00` |
| HW Ver | `0xcb00` |
| SW Ver | `0xe201` |
| SBC / SLA / DAA | False / False / False (sin protección de hardware) |

---

## Contenido del repositorio

| Archivo | Descripción |
|---|---|
| `validate_and_patch_uboot.py` | Valida SHA256 del original, aplica los 9 parches, verifica SHA256 de salida |
| `LK_PATCH_ANALYSIS.md` | Análisis técnico completo: desensamblado, rutas de código, historia de parches |
| `README.md` | Este archivo |

> **Nota:** Los binarios de firmware (`uboot_orig.bin`, etc.) no se incluyen — son propietarios de LG/MediaTek. Obtener de tu dispositivo o de un backup propio.

---

## Los 9 parches (v7)

La función de verificación en `0x01E17F48` tiene 4 rutas de código separadas. Todas deben ser silenciadas:

| Parche | File offset | Bytes originales | Bytes nuevos | Descripción |
|---|---|---|---|---|
| P1 | `0x181EC` | `C0 F2 EC 81` | `00 BF 00 BF` | NOP BLT.W — boot path, error tras verify1 |
| P2 | `0x18204` | `C0 F2 E5 81` | `00 BF 00 BF` | NOP BLT.W — boot path, error tras verify2 |
| P3 | `0x18342` | `C0 F2 3C 81` | `00 BF 00 BF` | NOP BLT.W — path A, error tras BL 0x01E01CFC |
| P4 | `0x18358` | `C0 F2 2C 81` | `00 BF 00 BF` | NOP BLT.W — path A, error tras BL 0x01E021F0 |
| P5 | `0x18382` | `C0 F2 DB 80` | `00 BF 00 BF` | NOP BLT.W — path B, error tras BL 0x01E01F9C |
| P6 | `0x18396` | `C0 F2 21 81` | `00 BF 00 BF` | NOP BLT.W — path B, error tras BL 0x01E0230C |
| P7 | `0x18556` | `46 DB` | `00 BF` | NOP BLT.N — recovery path C, error tras verify1 |
| P8 | `0x1856A` | `BF F6 16 AF` | `FF F7 16 BF` | BGE.W → B.W — recovery path C, fuerza éxito |
| P9 | `0x184E2` | `06 F0 E5 FD` | `00 20 00 BF` | BL 0x01E1EEB0 → MOVS R0,#0; NOP — post-load verify |

**P9 es el parche crítico final:** después de leer la imagen desde la partición flash, el LK llama a `0x01E1EEB0` que verifica la firma post-lectura. Para CWM (sin firma LG) retorna ≠0. P9 fuerza R0=0 antes del `CBZ R0, success`.

Ver `LK_PATCH_ANALYSIS.md` para el análisis completo con desensamblado.

---

## Por qué el stock bootloader tiene verificación de firmas

Aunque SBC/SLA/DAA son `False` (sin protección de hardware), el LK implementa verificación de firmas **por software**. El tipo de seguridad `security_type=0` tiene el bit 0 de la máscara `0xAB` seteado → activa verificación.

El error se muestra como bitmap en pantalla ("Security Error") — no aparece como string en el binario, lo que complica el análisis.

**Regla crítica:** no saltear la función `0x01E17F48` completa. Inicializa los globals BSS `0x01E44AA8` y `0x01E45AC0` que el executor de kernel necesita. Saltearla causa bootloop.

---

## Historia de parches

| Versión | Resultado | Causa del fallo |
|---|---|---|
| v1 | BOOTLOOP | desconocido |
| v2 | BOOTLOOP | saltaba `0x01E17F48` completa → globals BSS NULL → kernel executor falla |
| v3 | SECURITY ERROR en stock | saltaba a `0x01E18018` sin el setup previo (R9, estructuras de kernel) |
| v4 | stock OK ✓, CWM Security Error | solo P1+P2 — faltaban paths A, B, C y post-load verify |
| v5 | stock OK ✓, CWM Security Error | parcheaba verify fns para retornar 0, pero paths A/B/C usan funciones distintas |
| v6 | stock OK ✓, CWM Security Error | P1-P8 correctos, faltaba P9 (post-load verify `0x01E1EEB0`) |
| **v7** | **stock OK ✓ + CWM OK ✓** | **9 parches — verificado en hardware** |

---

## eMMC — Partición uboot

```
/proc/dumchar_info:  uboot  0x80000  0x1180000  2  /dev/block/mmcblk0
StartAddr: 0x1180000
Tamaño:    0x80000 = 524288 bytes = 1024 sectores de 512
dd seek:   0x1180000 / 512 = 35840
```

---

## Protocolo MTK Preloader (MT6575) — Notas de ingeniería

Esta sección documenta el trabajo realizado para flashear vía USB usando mtkclient, útil para otros dispositivos MT6575.

### Interfaces USB del dispositivo en modo preloader

| Iface | Clase | EPs | Uso |
|---|---|---|---|
| 0 | CDC Communications | EP81 (INT IN) | Control CDC |
| 1 | CDC Data | EP82 IN / EP02 OUT | No usable para MTK |
| **2** | **Vendor Specific** | **EP84 IN / EP04 OUT** | **Protocolo MTK preloader** |

El protocolo MTK corre en **Interface 2, EP4 OUT / EP84 IN** — no en la interfaz CDC.

### Handshake

```
Host → Device    Device → Host
0xa0         →   0x5f   (acknowledge)
0x0a         →   0xf5
0x50         →   0xaf
0x05         →   0xfa
```

**Problema:** Leer con buffer de 1 byte en un EP de 512 bytes causa `LIBUSB_ERROR_OVERFLOW`. Solución: leer con `wMaxPacketSize` (512) y usar un algoritmo drain-and-match que descarta bytes espontáneos de `0x5f`.

### DA (Download Agent) para MT6575

Archivo: `MTK_AllInOne_DA_mt6590.bin`  
Entry: `hw_code=0x6575, hw_ver=0xcb00, sw_ver=0xe201`

| Region | Offset en archivo | Tamaño | Load addr | Uso |
|---|---|---|---|---|
| 0 | `0x3E844` | `0x270` | `0xC2010000` | EMI config |
| **1** | **`0x3EAB4`** | **`0x217E0`** | **`0xC2000000`** | **Stage 1 (se sube)** |
| 2 | `0x60294` | `0x17D8` | `0xC2038000` | Stage 2 |

Checksum XOR de 16-bit words del DA: `0x655F`

### Flujo SEND_DA → JUMP_DA → Sync

```
Host: CMD 0xD7 (SEND_DA)    → Device echo: 0xD7
Host: address (big-endian)  → Device echo: address
Host: size                  → Device echo: size
Host: sig_len               → Device echo: sig_len
Device: status (0x0000 = OK)
Host: [sube 137,184 bytes del DA]
Device: checksum (0x655F) + status (0x0000)
Host: CMD 0xD5 (JUMP_DA)    → Device echo: 0xD5
Host: address (0xC2000000)  → Device echo: 0xC2000000
Device: jump status (0x0000 = OK)
Device: sync byte 0xC0      ← DA ejecutándose correctamente
```

### Parches necesarios en mtkclient para MT6575 / VID:PID 1004:61f1

**`mtkclient/config/usb_ids.py`:**
```python
0x1004: {0x6000: 2, 0x61f1: 2},  # Interface 2 = Vendor Specific con EP4/EP84
```

**`mtkclient/Library/Connection/usblib.py`:**  
Remover filtro `bDeviceClass` que excluía el dispositivo (clase 0xEF).

**`mtkclient/Library/Port.py` — `run_handshake()`:**
- Agregar `0x61f1` a `brom_pids` (evita `0xa0` extra antes del loop)
- Flush inicial con `maxinsize` (512), no 64, para evitar EOVERFLOW
- Algoritmo **drain-and-match** con buffer de 512 bytes:
  - Lee paquetes completos
  - En `i=0`: descarta bytes espontáneos de `0x5f`
  - En `i>0`: reset si hay desync

### Flujo correcto para mtkclient

1. `sudo udevadm control --stop-exec-queue` (desactivar hook udev)
2. Desconectar USB del teléfono
3. Ejecutar: `sudo python3 mtk.py w uboot uboot_patched_v7.bin`
4. mtkclient muestra: *"Waiting for PreLoader VCOM..."*
5. Conectar teléfono en modo descarga (Vol↑ + Vol↓ + USB)

> Si el teléfono está conectado cuando arranca mtkclient, `cdc.connect()` retorna True, salta el `init()` y sale con *"Please disconnect, start mtkclient and reconnect"*.

**Alternativa:** Octoplus LG Tool (de pago) funciona sin ninguno de estos parches.

---

## gettargetconfig output (MT6575 verificado)

```
Preloader - CPU:            MT6575/MT8317()
Preloader - HW code:        0x6575
Preloader - HW subcode:     0x8a00
Preloader - HW Ver:         0xcb00
Preloader - SW Ver:         0xe201
Preloader - SBC enabled:    False
Preloader - SLA enabled:    False
Preloader - DAA enabled:    False
```
