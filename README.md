# MMUKO QEMU Boot Scaffold

This turns the MMUKO boot idea into a tiny QEMU-bootable kernel.

Important distinction:

- `mmuko-boot.c` from the gist is a normal hosted C program. It uses `printf`,
  `malloc`, `calloc`, and the host OS C runtime.
- QEMU boots firmware, boot sectors, kernels, or disk images. At boot time there
  is no hosted C runtime, so MMUKO needs to run as freestanding code.

This scaffold supports two boot paths.

## Path A: Direct BIOS Boot On This Windows Machine

This path uses the tools already common in a MinGW + QEMU setup:

- `as`
- `gcc`
- `ld`
- `qemu-system-i386`

Build the raw boot image:

```powershell
.\build-direct.ps1
```

Run it:

```powershell
qemu-system-i386 -drive format=raw,file=build\mmuko-direct.img,if=ide,index=0 -display none -serial stdio -no-reboot
```

The kernel deliberately halts at the end, so QEMU will keep running until you
stop it with `Ctrl+C`.

The direct boot path works like this:

1. `boot16.s` starts as a 512-byte BIOS boot sector.
2. It loads `kernel-flat.bin` from disk LBA 1 into memory at `0x10000`.
3. It switches to 32-bit protected mode.
4. It jumps into `kernel-entry.s`.
5. `kernel-entry.s` calls `kernel_main()` in `kernel.c`.

## Path B: GRUB Multiboot

The GRUB path uses GRUB Multiboot as the loader:

1. GRUB starts the kernel in 32-bit protected mode.
2. `kernel_main()` initializes screen and serial output.
3. `mmuko_boot()` runs the MMUKO boot phases.
4. `mmuko_program_main()` runs after boot succeeds.

## Files

- `boot.asm` - Multiboot entry point and stack setup.
- `boot16.s` - Direct BIOS boot sector.
- `kernel-entry.s` - Direct boot flat-kernel entry point.
- `kernel.c` - Freestanding MMUKO boot model and example MMUKO program.
- `linker.ld` - Places the kernel at 1 MiB for GRUB.
- `linker-flat.ld` - Places the direct boot kernel at `0x10000`.
- `grub.cfg` - GRUB menu entry.
- `Makefile` - Builds an ISO and runs it in QEMU.
- `build-direct.ps1` - Builds the direct BIOS boot image on Windows.

## Toolchain

The easiest path on Windows is WSL or MSYS2 with:

- `nasm`
- `i686-elf-gcc`
- `grub-mkrescue`
- `grub-file`
- `xorriso`
- `qemu-system-i386`
- `make`

On a Debian/Ubuntu-like environment, QEMU/GRUB/NASM can usually be installed with:

```sh
sudo apt install make nasm grub-pc-bin grub-common xorriso qemu-system-x86
```

You still need an `i686-elf-gcc` cross compiler. If you do not have one yet,
use an OSDev-style cross compiler, or adapt the Makefile to your existing
freestanding i386 compiler.

## GRUB Build And Run

```sh
make
make run
```

QEMU will show VGA text, and the same log is also written to serial with
`-serial stdio`.

## Where To Write Your Program

Edit this function in `kernel.c`:

```c
static void mmuko_program_main(MMUKO_System *sys)
```

That function is the first MMUKO "program" in this scaffold. It only runs after
`mmuko_boot(sys)` returns `BOOT_OK`.

Later, you can replace it with a loader that reads a separate payload from disk
and jumps to it, but compiling the program into the kernel is the simplest way
to experiment with QEMU first.
