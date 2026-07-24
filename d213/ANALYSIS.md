# Análisis técnico: Parche LK bootloader LG D213 (MT6572)

**Estado (2026-07-24): parche flasheado y verificado en hardware real.**
Bootloader parcheado (readback SHA256 OK, stock arranca normal), TWRP
2.8.1.0 flasheado y arranca sin bloquearse (`ro.twrp.boot=1`,
`twrp.crash_counter=0`). El kernel imprime `"Boot Certificate Cannot Be
Verified!!!"` en dmesg al bootear TWRP, pero es solo informativo — no
impide el arranque, confirmando que el bypass en el LK es efectivo.

## Corrección: combinación de teclas para recovery (2026-07-24)

Las instrucciones originales de 4pda decían Vol− + Power para entrar a
recovery. Es **incorrecto** para este hardware. Se encontró el kernel
fuente oficial de LG para este dispositivo
(`LGD213CF/LGD213CF_v10a_Kernel`) y se confirmó en
`arch/arm/mach-mt6572/muse72_s4_kk/dct/dct/cust_kpd.h` (el board
`muse72_s4_kk` es el target de build indicado explícitamente en el
`README.TXT` del paquete):

```c
#define MT65XX_RECOVERY_KEY  1    /* KEY_VOLUMEUP */
#define MT65XX_FACTORY_KEY  10    /* KEY_VOLUMEDOWN */
```

**Recovery = Vol+ (arriba) + Power.** Vol− (abajo) + Power es el modo
FACTORY/descarga, no recovery. Los otros 3 boards del mismo paquete de
kernel (`muse72_phone`, `muse72_s2_kk0`, `muse72_s5_kk`) coinciden en el
mismo mapeo semántico, solo cambia el código de tecla interno (0/9 vs
1/10). No se encontró el source del LK/preloader en este paquete (solo
kernel Linux), pero el LK de MTK comparte el mismo `cust_kpd.h` generado
por DCT en su build, así que este archivo es autoritativo para la
combinación de boot real, no solo para el driver de teclado de Android.

## Origen del parche

El parche NO se derivó completo desde cero: se encontró un binario ya
parcheado (`lk_L50_D213_v10f_pathed.bin`) compartido en 4pda.ru por el
usuario `alekcacko`, para firmware **LGD213AT V10f**, ya verificado por él
en hardware real (TWRP arranca sin "Security Error").

Se comparó byte a byte contra el `uboot_raw.bin` dumpeado de este mismo
dispositivo: **solo difieren 8 bytes** (2
parches de 4 bytes cada uno) sobre un archivo de 524288 bytes idéntico en
todo lo demás. Esto confirma que es exactamente el mismo build de firmware,
no solo "el mismo modelo" — el parche es un match directo para este
dispositivo específico.

```
SHA256 uboot_raw.bin (original):  d5f9c078bab3ea3c0561c9153151132b886b422ced718e762979f7b5a4653045
SHA256 lk_L50_D213_v10f_pathed.bin: c6b7b8b327373462d6ec0b401f6c197b9b366411d5c8fbb542e3c199614607d6
```

## Los 2 parches (confirmados por diff + decodificación)

| # | File offset | Original | Parcheado | Qué hace |
|---|---|---|---|---|
| P1 | `0x19B5A` | `C0 F2 6F 81` (`BLT.W 0x19E3C`) | `00 20 00 20` (`MOVS R0,#0` x2) | Rama de error de un branch dentro del dispatcher de verificación (ver más abajo — es el mismo bloque de código de `0x198D8-0x19D82` que se había identificado por análisis estructural propio, pero un branch distinto al que se había mapeado ahí). |
| P2 | `0x2CFBC` | `04 46 78 B9` (`MOV R4,R0`; `CBNZ R0,→0x2CFE0`) | `00 24 00 20` (`MOVS R4,#0`; `MOVS R0,#0`) | Verificación post-lectura en una función distinta (probable verificación de certificado, dado el string sin usar `"Boot Certificate Cannot Be Verified!!!"` encontrado en el binario) — `0x2CFE0` es una salida de función que retorna `-1` (error); el parche fuerza `R0=0`/`R4=0` y elimina el salto, cayendo siempre a la ruta de continuación. |

Reproducido con `validate_and_patch_uboot.py` — el resultado es **byte a
byte idéntico** al archivo de 4pda.

## Contexto: investigación estructural propia (previa al hallazgo del parche real)

Antes de encontrar el parche de 4pda se hizo un análisis estructural desde
cero (sin firmas de bytes reusables del E450/E440, porque este es MT6572 —
generación de chip distinta, código genuinamente recompilado, ver historial
de este documento en git). Se encontró correctamente la **zona** del
dispatcher de verificación (`0x198D8`–`0x19D82`, 6 funciones de verificación
confirmadas por prólogo real), pero el conjunto exacto de branches que
importan resultó ser más chico y distinto al que se había hipotetizado por
analogía con el E450 (9 NOP + 1 forzado). El parche real de 4pda usa solo
**2 branches en 2 funciones distintas** — mucho más quirúrgico. Se mantiene
esto como nota: la heurística estructural (clustering de `BL+CMP0+BLT/BGE`)
sirvió para ubicar la zona correcta, pero no reemplaza la verificación
empírica en hardware real.

## Checklist

- [x] Backup del `uboot`/`recovery`/`boot`/`preloader`/`seccfg` originales
      (guardados localmente, SHA256 verificado).
- [x] Parche flasheado vía ADB+root (`/dev/uboot`, no `/dev/block/mmcblk0` —
      el nodo directo existe en este dispositivo).
- [x] SHA256 de readback verificado (coincide con el parche de 4pda).
- [x] ROM stock confirmada arrancando con normalidad tras el parche.
- [x] TWRP 2.8.1.0 flasheado en `/dev/recovery` y confirmado arrancando sin
      bloquearse.
- [x] Vuelta a sistema confirmada estable (root y ADB funcionando).

**Nota de troubleshooting (no necesitada acá, pero documentada):** si
aparece `ERROR: Boot cerification verify <-1>` al entrar al recovery
modificado, significa que el parche del bootloader no se aplicó — hay que
re-flashear `/dev/uboot` (según la nota original del autor en 4pda).
