# LG D213 (L50, MT6572) LK Bootloader Patch — Unsigned Recovery Boot

Parche para el bootloader LK del **LG Optimus L50 (D213)** que permite
bootear recoveries no firmados (TWRP) sin "Security Error", sin romper el
boot de la ROM stock.

**Origen:** parche ya verificado en hardware, compartido por el usuario
`alekcacko` en 4pda.ru para firmware **LGD213AT V10f**. Confirmado por
comparación byte a byte contra el dump propio del dispositivo — el parche
es un match exacto (ver `ANALYSIS.md`).

**Estado (2026-07-24): parche flasheado y verificado en el dispositivo real,
objetivo completo.** Bootloader parcheado, readback por SHA256 coincide,
stock sigue arrancando con normalidad. TWRP 2.8.1.0 flasheado en
`/dev/recovery` y **arranca correctamente** (`ro.twrp.boot=1`,
`init.svc.recovery=running`, `twrp.crash_counter=0`) — el kernel todavía
loguea `"Boot Certificate Cannot Be Verified!!!"` en dmesg pero es
informativo, no bloquea el boot. Vuelta a sistema confirmada (root y ADB
funcionando con normalidad tras el ciclo completo).

---

## Hardware confirmado

| Campo | Valor |
|---|---|
| Modelo | `LG-D213` (`ro.product.model`) |
| Codename | `luv50ss` |
| Android | 4.4.2 (KitKat) |
| SoC | MediaTek MT6572 |
| Root | `/system/xbin/su` (el `/system/bin/su` más nuevo del dispositivo da "Permission denied" — usar el path viejo explícito) |

## Nodos de dispositivo directos (más simple que calcular skip/seek sobre mmcblk0)

```
/dev/uboot     crw------- root root  (partición uboot, 524288 bytes)
/dev/recovery  crw-r----- root system (partición recovery)
```

## Backups originales

Guardados localmente (fuera de este repositorio, son binarios propietarios):
`uboot_raw.bin`, `boot_raw.img`, `recovery_raw.img`, más `preloader_raw.bin`
(mmcblk0boot0) y `seccfg_raw.bin` (partición completa en cero — no usa el
mecanismo de lock por software).

```
SHA256 uboot_raw.bin: d5f9c078bab3ea3c0561c9153151132b886b422ced718e762979f7b5a4653045
```

## Regenerar el parche

```bash
# Requiere uboot_raw.bin (dump propio de tu dispositivo, ver "Flashear" abajo)
python3 validate_and_patch_uboot.py uboot_raw.bin uboot_patched.bin
```

Ver `ANALYSIS.md` para el detalle de los 2 parches.

## Flashear vía ADB (root ya obtenido)

```bash
# Backup ya hecho, pero re-verificar antes de escribir:
adb shell "su -c 'dd if=/dev/uboot of=/data/local/tmp/uboot_bak_check.bin'"
adb pull /data/local/tmp/uboot_bak_check.bin /tmp/uboot_bak_check.bin
sha256sum /tmp/uboot_bak_check.bin   # debe coincidir con d5f9c078bab3ea3c0561c9153151132b886b422ced718e762979f7b5a4653045

# Flash
adb push uboot_patched.bin /data/local/tmp/uboot_patched.bin
adb shell "su -c 'dd if=/data/local/tmp/uboot_patched.bin of=/dev/uboot && sync'"
adb shell "su -c 'rm /data/local/tmp/uboot_patched.bin /data/local/tmp/uboot_bak_check.bin'"

# Verificar (SHA256 debe coincidir con uboot_patched.bin, c6b7b8b327373462d6ec0b401f6c197b9b366411d5c8fbb542e3c199614607d6)
adb shell "su -c 'dd if=/dev/uboot of=/data/local/tmp/rb.bin'"
adb pull /data/local/tmp/rb.bin && sha256sum rb.bin

# Reiniciar y confirmar que la ROM stock sigue arrancando ANTES de flashear recovery
adb reboot
```

## Flashear recovery (TWRP) — solo después de confirmar que el bootloader parcheado no rompió el boot stock

```bash
adb push TWRP_2.8.1.0_LG_L50.img /data/local/tmp/recovery.img
adb shell "su -c 'dd if=/data/local/tmp/recovery.img of=/dev/recovery && sync'"
```

## Entrar a recovery

- **Desde apagado:** mantener Vol− + Power, soltar al ver el logo y volver a
  presionar inmediatamente. Navegación con volumen, selección con doble
  toque de Power. Aceptar el reset (los datos NO se borran — solo se borran
  con el recovery stock).
- **Desde el sistema (con root):** `adb shell "su -c 'reboot recovery'"`.

## Troubleshooting

Si al entrar al recovery modificado aparece en pantalla
`ERROR: Boot cerification verify <-1>`, significa que el bootloader
parcheado **no** se flasheó correctamente — arrancar a sistema y reflashear
`/dev/uboot`.

Para ADB en modo recovery hacen falta los drivers correspondientes.

## Nota sobre el recovery (TWRP) portado

El recovery de 4pda fue portado desde el LG L60 y el autor reporta
problemas con el almacenamiento interno (no se guardan configuraciones,
"L60 no es un donor adecuado"). Si se busca portar un recovery propio,
conviene partir de un donante con partición interna FAT y procesador
MT65x2 (ej. L Bello, Leon), respetar que el tamaño no supere ~10MB, y
ajustar el `updater-script` al layout de particiones real de este
dispositivo (distinto al de otros modelos MTK).
