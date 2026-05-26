/* Flat-kernel entry for the direct BIOS boot path. */

.intel_syntax noprefix
.code32
.global _start
.extern _kernel_main

_start:
    push 0
    push 0
    call _kernel_main

.halt:
    cli
    hlt
    jmp .halt
