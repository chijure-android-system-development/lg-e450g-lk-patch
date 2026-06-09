# Análisis técnico: Parche LK bootloader LG E450 (MT6575)

## Objetivo

Permitir el boot de recoveries no firmados (CWM, TWRP) en el LG E450g sin modificar el hardware ni pagar por herramientas de pago cada vez.

## Estructura del binario LK

```
uboot_orig.bin (524,288 bytes = 0x80000)
├── Header:    file 0x000–0x1FF  (no se mapea en RAM)
└── Código:    file 0x200–0x43F04 (VMA 0x01E00000–0x01E43D04)
    BSS:       VMA 0x01E43F04 en adelante (extiende en RAM)
```

Conversión de offset a dirección virtual:
```
vma  = file_offset + 0x01E00000 - 0x200
file = vma         - 0x01E00000 + 0x200
```

## Flujo de boot del LK (simplificado)

```
BROM → Preloader → LK (uboot partition) → Kernel → Android
```

El LK corre en `0x01E00000`. Carga el kernel desde la partición `boot`, verifica la firma y salta a él.

## El chequeo de seguridad SW

La función en `0x01E17F48` (file `0x181A8`) decide si el kernel puede bootear:

```asm
; --- Entrada al bloque de verificación ---
0x01E17FC2: LDR.W R3, [R8]        ; R8 → BSS: security_type (= 0 en este dispositivo)
0x01E17FC6: CMP   R3, #7
0x01E17FC8: BHI.N 0x01E18018      ; si type > 7 → saltar (casos inválidos/debug)

; --- Para type=0: evaluar si se requiere verificación ---
0x01E17FCA: MOVS  R2, #1
0x01E17FCC: LSLS.W R3, R2, R3     ; R3 = 1 << security_type  (= 1 para type=0)
0x01E17FD0: TST.W  R3, #0xAB      ; 0xAB = 10101011b  → bit0 SET → ZF=0
0x01E17FD4: BEQ.W  0x01ED8124     ; ZF=0 → NO salta → type=0 SÍ requiere verificación

; --- Llamada 1: verify_image ---
0x01E17FD8: (setup parámetros)
0x01E17FE6: BL    0x01E01A18      ; verify_image(kernel_image)
0x01E17FEA: CMP   R0, #0
0x01E17FEC: BLT.W 0x01ED83C8     ; si R0 < 0 → "Security Error" + halt  ← PATCH1

; --- Llamada 2: segunda verificación ---
0x01E17FF0: (setup parámetros)
0x01E17FFE: BL    0x01E020D4      ; verify_image2(kernel_image)
0x01E18002: CMP   R0, #0
0x01E18004: BLT.W 0x01ED83D2     ; si R0 < 0 → "Security Error" + halt  ← PATCH2

; --- Setup crítico de boot ---
0x01E18008: MOV   R0, R9          ; R9 = descriptor de imagen cargada en RAM
0x01E1800A: BL    0x01E07FFC      ; prepara parámetros de kernel
0x01E1800E: MOV   R1, R0
0x01E18014: BL    0x01E1BEDC      ; carga/prepara imagen final
; → continúa en 0x01E18018: transferencia al kernel
```

La máscara `0xAB = 10101011b` define qué security_types requieren verificación:
- **Bit 0 (type 0):** SET → requiere firma   ← nuestro dispositivo
- **Bit 1 (type 1):** SET → requiere firma
- **Bit 2 (type 2):** NO set → salta verificación (ruta BSS callback)
- **Bit 3 (type 3):** SET → requiere firma
- ...

## Historia de parches

### v2 — BOOTLOOP

Modificaba 3 bytes para saltar la función `0x01E17F48` por completo.

Problema: esa función inicializa los globals BSS en `0x01E44AA8` y `0x01E45AC0`. La función `0x01E09DC8` (executor del kernel) lee esos globals y retorna -1 si son NULL → LK reinicia → bootloop infinito.

```
file 0x18707: D0 → E0  (BEQ.N → B.N — salta la llamada a 0x01E17F48)
file 0x2CBF8: 28 46    (NOP)
file 0x2CBF9: ...
```

### v3 — SECURITY ERROR (en ROM stock)

Modificaba 1 byte para hacer `BHI.N → B.N` en la prueba `security_type > 7`.

```
file 0x181C9: D8 → E0
```

Resultado: `security_type=0` también saltaba a `0x01E18018`, pero **sin haber ejecutado los pasos `0x01E17FD8–0x01E18014`** que configuran R9, el descriptor de imagen y las estructuras de kernel en RAM. El código en `0x01E18018` operaba sobre estado no inicializado → "Security Error" **incluso con ROM stock**.

Diagnóstico: `0x01E18018` NO es un kernel load path independiente; es el punto de llegada después de que todo el setup ya corrió.

### v5 — FALLIDO (Security Error en CWM)

Hacía que `verify_image` (#1 y #2) retornen 0 inmediatamente (MOVS R0,#0; BX LR). Funcionaba para la ruta de boot, pero la ruta de recovery pasa por **path A** y **path B** que llaman funciones completamente distintas (0x01E01CFC, 0x01E021F0, 0x01E01F9C, 0x01E0230C) — esas funciones nunca fueron tocadas.

```
file 0x1C18: 00 20 70 47  (MOVS R0,#0; BX LR — parcha 0x01E01A18)
file 0x22D4: 00 20 70 47  (MOVS R0,#0; BX LR — parcha 0x01E020D4)
```

### v6 — FALLIDO (aún Security Error en CWM)

Parcheaba 8 ramas BLT.W/BLT.N/BGE.W en paths A, B y C. Pero quedaba sin parchear la ruta de carga de partición que termina en un verificador post-lectura (`BL 0x01E1EEB0` → `CBZ R0`).

### v7 — CORRECTO ✓ (verificado en hardware 2026-06-09)

**Descubrimiento clave:** después de que `BLX R1` (lectura de la imagen desde la partición recovery) la función llama a `0x01E1EEB0` que verifica la firma DESPUÉS de leer. La secuencia es:

```asm
0x01E182E2: BL  0x01E1EEB0   ; verificador post-carga (retorna ≠0 si firma inválida)
0x01E182E6: CBZ R0, success  ; si R0==0 → éxito, si R0≠0 → cae al error
0x01E182E8: LDR R0, [PC,...] ; → carga dirección de string de error
0x01E182EC: BL  0x01E1BEDC   ; → display Security Error + halt
```

Para CWM sin firma LG: `0x01E1EEB0` retorna non-zero → `CBZ` no tomado → Security Error.

**Mapa completo de rutas de verificación en `0x01E17F48`:**

```
entry:
  TST → BNE.N → path_B (0x1836E)
  LSL; BPL.W  → kernel directo (sin verify — si bit correcto)
  [fall-through] → path_A

path_A [0x1832C–0x1836C]:
  BL 0x01E01CFC → BLT.W error (0x18342) ← P3
  BL 0x01E021F0 → BLT.W error (0x18358) ← P4
  boot_setup → kernel

path_B [0x1836E–0x183AA]:
  BL 0x01E01F9C → BLT.W error (0x18382) ← P5
  BL 0x01E0230C → BLT.W error (0x18396) ← P6
  boot_setup → kernel

path_C [0x18540–0x18576]:  (recovery)
  BL 0x01E01A18 → BLT.N error (0x18556) ← P7
  BL 0x01E020D4 → BGE.W success (0x1856A) ← P8

partition-load path [0x183AC–0x185A0]:  (carga desde flash)
  BL  0x01E02AA8  ; abrir partición
  BL  0x01E02994  ; obtener buffer en RAM
  BLX R1          ; leer datos (función ptr en struct de partición)
  BLT.N 0x184B6   ; error si lectura falla (no parcheado — lectura debería pasar)
  BL  0x01E1EE90  ; procesado post-lectura
  BL  0x01E1EEB0  ; verificar firma post-lectura ← P9: MOVS R0,#0; NOP
  CBZ R0, success ; si R0==0 → éxito
  → BL 0x01E1BEDC ; error display + halt  (alcanzable si P9 no aplicado)
```

**9 parches:**

```
file 0x181EC: C0 F2 EC 81 → 00 BF 00 BF  (P1 boot  BLT.W→NOP tras BL 0x01E01A18)
file 0x18204: C0 F2 E5 81 → 00 BF 00 BF  (P2 boot  BLT.W→NOP tras BL 0x01E020D4)
file 0x18342: C0 F2 3C 81 → 00 BF 00 BF  (P3 pathA BLT.W→NOP tras BL 0x01E01CFC)
file 0x18358: C0 F2 2C 81 → 00 BF 00 BF  (P4 pathA BLT.W→NOP tras BL 0x01E021F0)
file 0x18382: C0 F2 DB 80 → 00 BF 00 BF  (P5 pathB BLT.W→NOP tras BL 0x01E01F9C)
file 0x18396: C0 F2 21 81 → 00 BF 00 BF  (P6 pathB BLT.W→NOP tras BL 0x01E0230C)
file 0x18556: 46 DB       → 00 BF        (P7 recov BLT.N→NOP tras BL 0x01E01A18)
file 0x1856A: BF F6 16 AF → FF F7 16 BF  (P8 recov BGE.W→B.W fuerza exito)
file 0x184E2: 06 F0 E5 FD → 00 20 00 BF  (P9 load  BL 0x01E1EEB0→MOVS R0,#0;NOP)
```

Archivo: `uboot_patched_v7.bin`  
SHA256:   `973e0ed498917d3ec86dc10d3e1c53357980dfd4df43ced09aa51c644df7e99a`

**Comportamiento verificado:**

| Imagen | Resultado |
|---|---|
| ROM stock firmada | boot normal ✓ (verify pasa, ramas de error nunca tomadas) |
| CWM 6.0.4.4 sin firma | boot CWM ✓ (verify falla pero P1-P9 silencian todas las rutas de error) |

### v4 — CORRECTO ✓ (verificado en hardware 2026-06-09)

**Principio:** dejar correr todo el flujo (incluyendo `verify_image`), y silenciar únicamente las ramas de error que de otro modo mostrarían "Security Error" y halterían el boot.

```
file 0x181EC–0x181EF:  C0 F2 EC 81  →  00 BF 00 BF   (BLT.W → NOP NOP)
file 0x18204–0x18207:  C0 F2 E5 81  →  00 BF 00 BF   (BLT.W → NOP NOP)
```

Archivo: `uboot_patched_v4.bin`  
SHA256:   `05ada3e23ecc6e5fbeb62be1a125d10eedfa7d724e2b0ad5c30e38878fea144b`

**Comportamiento esperado:**

| Imagen | verify_image retorna | BLT.W | Resultado |
|---|---|---|---|
| ROM stock firmada | 0 (pass) | no se toma (igual que antes) | boot normal ✓ |
| CWM sin firma LG  | -1 (fail) | NOP'd → continúa | boot CWM ✓ |

Las dos llamadas `verify_image` aún corren (pueden loggear errores a UART), lo que garantiza que R9 y el estado de las estructuras de kernel estén correctamente inicializados antes de llegar a `0x01E18018`.

## Cómo generar el parche (v7 — final)

Usar `validate_and_patch_uboot.py` en el mismo directorio:

```bash
python3 validate_and_patch_uboot.py uboot_orig.bin uboot_patched_v7.bin
```

O manualmente:

```python
with open('uboot_orig.bin', 'rb') as f:
    data = bytearray(f.read())

patches = [
    (0x181EC, b'\x00\xBF\x00\xBF'),  # P1
    (0x18204, b'\x00\xBF\x00\xBF'),  # P2
    (0x18342, b'\x00\xBF\x00\xBF'),  # P3
    (0x18358, b'\x00\xBF\x00\xBF'),  # P4
    (0x18382, b'\x00\xBF\x00\xBF'),  # P5
    (0x18396, b'\x00\xBF\x00\xBF'),  # P6
    (0x18556, b'\x00\xBF'),          # P7
    (0x1856A, b'\xFF\xF7\x16\xBF'),  # P8
    (0x184E2, b'\x00\x20\x00\xBF'),  # P9
]
for off, new in patches:
    data[off:off+len(new)] = new

with open('uboot_patched_v7.bin', 'wb') as f:
    f.write(data)
```

## Cómo flashear (ADB + root)

```bash
# Backup
adb shell "su -c 'dd if=/dev/block/mmcblk0 bs=512 skip=35840 count=1024 of=/data/local/tmp/uboot_bak.bin && chmod 644 /data/local/tmp/uboot_bak.bin'"
adb pull /data/local/tmp/uboot_bak.bin uboot_backup.bin

# Flash v7
adb push uboot_patched_v7.bin /data/local/tmp/uboot_v7.bin
adb shell "su -c 'dd if=/data/local/tmp/uboot_v7.bin of=/dev/block/mmcblk0 bs=512 seek=35840 && sync'"
adb shell "su -c 'rm /data/local/tmp/uboot_v7.bin /data/local/tmp/uboot_bak.bin'"

# Readback para verificar
adb shell "su -c 'dd if=/dev/block/mmcblk0 bs=512 skip=35840 count=1024 of=/data/local/tmp/rb.bin && chmod 644 /data/local/tmp/rb.bin'"
adb pull /data/local/tmp/rb.bin && sha256sum rb.bin
# Esperado: 973e0ed498917d3ec86dc10d3e1c53357980dfd4df43ced09aa51c644df7e99a

# Reboot a recovery para probar CWM
adb reboot recovery
```

## Referencia rápida: offsets clave (v7)

| VMA | File offset | Parche | Descripción |
|---|---|---|---|
| `0x01E17FEC` | `0x181EC` | P1 NOP | BLT.W error tras verify_image1 (boot path) |
| `0x01E18004` | `0x18204` | P2 NOP | BLT.W error tras verify_image2 (boot path) |
| `0x01E18142` | `0x18342` | P3 NOP | BLT.W error tras BL 0x01E01CFC (path A) |
| `0x01E18158` | `0x18358` | P4 NOP | BLT.W error tras BL 0x01E021F0 (path A) |
| `0x01E18182` | `0x18382` | P5 NOP | BLT.W error tras BL 0x01E01F9C (path B) |
| `0x01E18196` | `0x18396` | P6 NOP | BLT.W error tras BL 0x01E0230C (path B) |
| `0x01E18356` | `0x18556` | P7 NOP | BLT.N error tras verify1 (recovery path C) |
| `0x01E1836A` | `0x1856A` | P8 B.W | BGE.W→B.W fuerza success (recovery path C) |
| `0x01E182E2` | `0x184E2` | P9 R0=0 | BL 0x01E1EEB0→MOVS R0,#0 (post-load verify) |
| `0x01E1800A` | `0x1820A` | — | BL 0x01E07FFC — boot setup (NO saltear) |
| `0x01E18014` | `0x18214` | — | BL 0x01E1BEDC — kernel prepare (NO saltear) |
