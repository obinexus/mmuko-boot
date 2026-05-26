/* Direct BIOS boot sector for MMUKO.
 * This path avoids GRUB and loads the flat kernel from LBA 1 to 0x10000.
 */

.intel_syntax noprefix
.code16
.global _start

KERNEL_LOAD_SEG = 0x1000
KERNEL_LOAD_OFF = 0x0000
KERNEL_SECTORS = 64

_start:
    cli
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 0x7C00
    sti

    mov byte ptr [boot_drive], dl
    mov si, offset loading_msg
    call print_string

    mov ah, 0x42
    mov dl, byte ptr [boot_drive]
    mov si, offset disk_address_packet
    int 0x13
    jc disk_error

    cli
    lgdt [gdt_descriptor]
    mov eax, cr0
    or eax, 1
    mov cr0, eax
    ljmp 0x08, protected_entry

disk_error:
    mov si, offset disk_error_msg
    call print_string
.halt16:
    hlt
    jmp .halt16

print_string:
    lodsb
    test al, al
    jz .done
    mov ah, 0x0E
    mov bx, 0x0007
    int 0x10
    jmp print_string
.done:
    ret

boot_drive:
    .byte 0

loading_msg:
    .asciz "MMUKO direct boot loading...\r\n"

disk_error_msg:
    .asciz "MMUKO disk read failed\r\n"

.align 4
disk_address_packet:
    .byte 0x10
    .byte 0
    .word KERNEL_SECTORS
    .word KERNEL_LOAD_OFF
    .word KERNEL_LOAD_SEG
    .quad 1

.align 8
gdt_start:
    .quad 0x0000000000000000
    .quad 0x00CF9A000000FFFF
    .quad 0x00CF92000000FFFF
gdt_end:

gdt_descriptor:
    .word gdt_end - gdt_start - 1
    .long gdt_start

.code32
protected_entry:
    mov ax, 0x10
    mov ds, ax
    mov es, ax
    mov fs, ax
    mov gs, ax
    mov ss, ax
    mov esp, 0x90000
    jmp 0x10000

.org 510
    .word 0xAA55
