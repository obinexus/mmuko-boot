; MMUKO Multiboot entry point.
; GRUB loads this kernel and jumps to _start in 32-bit protected mode.

MBALIGN  equ 1 << 0
MEMINFO  equ 1 << 1
FLAGS    equ MBALIGN | MEMINFO
MAGIC    equ 0x1BADB002
CHECKSUM equ -(MAGIC + FLAGS)

section .multiboot
align 4
    dd MAGIC
    dd FLAGS
    dd CHECKSUM

section .bss
align 16
stack_bottom:
    resb 16384
stack_top:

section .text
global _start
extern kernel_main

_start:
    mov esp, stack_top

    ; C calling convention: kernel_main(multiboot_magic, multiboot_info).
    push ebx
    push eax
    call kernel_main

.hang:
    cli
    hlt
    jmp .hang
