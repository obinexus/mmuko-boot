ENTRY(_start)

SECTIONS
{
    . = 0x10000;

    .text : {
        *(.text*)
        *(.rdata*)
        *(.rodata*)
    }

    .data : {
        *(.data*)
    }

    .bss : {
        *(COMMON)
        *(.bss*)
    }
}
