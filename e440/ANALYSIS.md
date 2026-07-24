# Análisis técnico: Parche LK bootloader LG E440 (MT6575)

## Objetivo

Permitir el boot de recoveries no firmados (CWM, TWRP) en el LG E440g, aplicando
la misma técnica ya verificada en hardware en el E450 (ver
[`../LK_PATCH_ANALYSIS.md`](../LK_PATCH_ANALYSIS.md)),
pero re-derivando los offsets sobre el binario propio del E440 en vez de asumir
que son iguales.

## Paso 1 — ¿Es el mismo binario, solo relocado?

Comparación directa `uboot_raw.bin` (E440) vs `uboot_orig.bin` (E450):

```
Tamaño: 524288 bytes en ambos (idéntico)
SHA256: distintos (firmwares distintos, como se esperaba)
cmp -l: 263291 bytes distintos de 524288 (~50%)
Campo @file offset 4 (tamaño de código, LE u32):
  e450: 0x00043d04
  e440: 0x0004423fc  (ligeramente distinto -> build distinto, no el mismo binario)
```

Conclusión: **no** es el mismo binario byte a byte, hay que re-derivar offsets.
Pero ambos comparten la cabecera `LK` idéntica (mismo formato MediaTek), lo
que sugiere fuertemente el mismo framework/toolchain y muy probablemente el
mismo código fuente para la lógica de seguridad (LG reutiliza el mismo BSP
MTK entre modelos de la serie L II).

## Paso 2 — Localizar funciones clave por firma de bytes

Se extrajeron los primeros 8-16 bytes de cada función de interés desde el
binario **ya analizado** del E450 (usando sus VMAs conocidas de
`LK_PATCH_ANALYSIS.md`) y se buscaron como bytes exactos dentro del binario
del E440:

| Función | E450 file offset | E440 file offset (encontrado) | Firma (8B) |
|---|---|---|---|
| `check_security` (función completa) | `0x18148` | `0x16118` | `2de9f04f87b00020` |
| `verify_image1` | `0x01C18` | `0x01BDC` | `2de9f04784b0984d` |
| `verify_image2` | `0x022D4` | `0x02298` | `2de9f04f83b0384c` |
| `pathA_func1` | `0x01EFC` | `0x01EC0` | `2de9f04f83b0894d` |
| `pathA_func2` | `0x023F0` | `0x023B4` | `2de9f04f83b0384c` (coincide con verify_image2, distinta ocurrencia) |
| `pathB_func2` | `0x0250C` | `0x024D0` | `08b5144b14487b44` |
| `postload_process` | `0x1F090` | `0x1CD74` | `0549002000b50246` |
| `postload_verify` | `0x1F0B0` | `0x1CD94` | `2de9f04ff1b07a9c` |
| `boot_setup` | `0x081FC` | `0x08004` | `10b50446fff7c6ff` |
| `kernel_prepare` | `0x1C0DC` | `0x19DC0` | `0fb400b583b004ab` |

Todas fueron coincidencias **únicas** (un solo hit en todo el binario de
524KB), salvo `pathB_func1`, que no apareció con la firma de 8-16 bytes
(probablemente difiere en una constante embebida cerca del inicio de la
función — dirección de literal pool, distinta por estar en otra ubicación).
Se encontró igualmente por desensamblado directo en el Paso 3 (ver más abajo,
`0x02160`, confirmado porque el `BL` hacia esa dirección aparece exactamente
donde correspondía estructuralmente).

Nota sobre el delta: el offset de `check_security` cambia en `-0x2030`
respecto al E450 (`0x18148 → 0x16118`), y ese mismo delta aplica a
`verify_image1`, `verify_image2`, `pathA_func1` — pero **no** a las
funciones más internas del cuerpo de `check_security` (paths B, post-load),
confirmando que es una recompilación real y no una simple relocación
uniforme de todo el archivo.

## Paso 3 — Desensamblar `check_security` completa en el E440

Con el desensamblador Thumb-2 propio (`e450/analyze_bootloader.py`, portado a
módulo reusable), se desensambló `0x16118`–`0x16618` del binario del E440.
Se confirmó la misma estructura que el E450:

```
entry (0x16118): setup, TST.W R3,#0xAB (0x161A0) — mismo chequeo de security_type
  BEQ.W → path directo sin verify (fall-through normal)

boot path (0x161A8–0x161D8):
  BL verify_image1 (file 0x01BDC) → CMP R0,#0 → BLT.W 0x163D4   <- P1
  BL verify_image2 (file 0x02298) → CMP R0,#0 → BLT.W 0x163DE   <- P2

path A (0x16328–0x16354):
  BL pathA_func1 (file 0x01EC0) → CMP R0,#0 → BLT.W 0x163CA     <- P3
  BL pathA_func2 (file 0x023B4) → CMP R0,#0 → BLT.W 0x163C0     <- P4

path B (0x16366–0x16392):
  BL pathB_func1 (file 0x02160, hallado por posición) → CMP R0,#0 → BLT.W 0x16348  <- P5
  BL pathB_func2 (file 0x024D0) → CMP R0,#0 → BLT.W 0x163E8     <- P6

recovery path C (0x1654E–0x1657C):
  BL verify_image1 (3ra vez) → CMP R0,#0 → BLT.N 0x163F0        <- P7
  BL verify_image2 (3ra vez) → CMP R0,#0 → BGE.W 0x16192        <- P8

partition-load path (0x16480–0x164E6):
  BL abrir partición (0x02A6C) ; BL obtener buffer (0x02958)
  BLX R1  (leer datos — función ptr en struct de partición)
  BLT.N 0x16390   ; error si lectura falla (NO parcheado — igual que E450)
  BL postload_process (file 0x1CD74)
  BL postload_verify  (file 0x1CD94) → CBZ R0, success           <- P9 (parchea el BL, no el CBZ)
```

Estructura **idéntica** a la del E450 (mismas 4 rutas + verificador
post-carga, mismo orden, mismos tipos de instrucción en cada punto de
decisión), solo con offsets y direcciones de error handler distintos.

## Paso 4 — Verificación de bytes antes de patchear

Cada uno de los 9 offsets candidatos se verificó programáticamente contra
el binario real del E440 antes de generar el parche (ver
`validate_and_patch_uboot.py`, que aborta si algún byte no coincide con lo
esperado):

```
file=0x161BC  BLT.W 0x01E163D4   [P1]  bytes=c0f20a82  OK
file=0x161D4  BLT.W 0x01E163DE   [P2]  bytes=c0f20382  OK
file=0x1633A  BLT.W 0x01E163CA   [P3]  bytes=c0f24681  OK
file=0x16350  BLT.W 0x01E163C0   [P4]  bytes=c0f23681  OK
file=0x1637A  BLT.W 0x01E16348   [P5]  bytes=c0f2e580  OK
file=0x1638E  BLT.W 0x01E163E8   [P6]  bytes=c0f22b81  OK
file=0x16562  BLT.N 0x01E163F0   [P7]  bytes=46db      OK
file=0x16576  BGE.W 0x01E16192   [P8]  bytes=bff60caf  OK
file=0x164E2  BL    0x01E1CB94   [P9]  bytes=06f057fc  OK  (postload_verify)
```

Todos los offsets coinciden exactamente con el tipo y target de instrucción
esperado según el mapeo estructural del Paso 3 — no son coincidencias de
bytes al azar, son los mismos puntos de decisión que en el E450.

## Paso 5 — Codificación del parche P8 (BGE.W → B.W)

A diferencia de las otras 8 ramas (que se silencian con NOP porque saltar
esas ramas de error implica caer al camino de éxito), la rama en P8 es al
revés: `BGE.W` salta **al éxito** cuando `R0 >= 0`; si simplemente se
convierte en NOP, el flujo **siempre caería al error** (regresión respecto
al comportamiento actual). La solución (igual que en el E450 v7) es convertir
la rama condicional en una rama incondicional `B.W` **al mismo target**.

Se escribió un codificador Thumb-2 T4 (`B.W`) y se validó *antes* de usarlo
contra el E440, reproduciendo el parche ya verificado en hardware del E450:

```
Input:  offset original de BGE.W en e450 (file 0x1856A) = -0x1d4
Output esperado (v7, verificado en hardware): FF F7 16 BF
Output del codificador: FF F7 16 BF   ✓ coincide exactamente
```

Con el codificador validado, se aplicó al caso del E440:

```
Input:  offset original de BGE.W en e440 (file 0x16576) = -0x1e8
Output: FF F7 0C BF   (mismo target final: VMA 0x01E16192, preservado)
```

## Resultado

Archivo: `uboot_patched_v1.bin`
SHA256 original:    `79c7148274a19e1159a302462d0b7ee4ffbd5d764e8a8ca012aa59057b62251c`
SHA256 parcheado:   `49427f704d95b09fac8b172e5d18cb83cdb26c612b578ffee364c5a8acee0c79`

**Aún no probado en hardware.** A diferencia del E450 (que llegó a v7 después
de 6 iteraciones fallidas *en el dispositivo real*, incluyendo un bootloop),
este parche del E440 se generó completamente offline por analogía
estructural y verificación cruzada de bytes — no hay iteraciones previas de
prueba-error en este hardware. El razonamiento es sólido (misma función,
mismos 9 puntos de decisión, mismo principio de "dejar correr todo el flujo
y silenciar solo las ramas de error"), pero **conlleva más incertidumbre que
reflashear un parche ya probado**. Se recomienda:

1. Tener el backup original (`uboot_raw.bin`, SHA256 ya verificado) a mano.
2. Tener mtkclient listo en modo Preloader como plan de contingencia (no
   depende de que Android arranque).
3. Flashear, verificar SHA256 de readback, y reiniciar probando primero que
   la ROM stock siga arrancando con normalidad antes de probar cualquier
   recovery no firmado.

**Actualización (2026-07-23):** parche flasheado en hardware real. Stock
sigue arrancando con normalidad y un recovery TWRP no firmado arranca
correctamente sin "Security Error" — el razonamiento offline de este
análisis quedó confirmado sin necesidad de iteraciones adicionales.
