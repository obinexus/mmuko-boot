CROSS ?= i686-elf-
CC := $(CROSS)gcc
AS := nasm
QEMU ?= qemu-system-i386

BUILD := build
ISO_DIR := $(BUILD)/iso
KERNEL := $(BUILD)/mmuko-kernel.bin
ISO := $(BUILD)/mmuko.iso

CFLAGS := -std=gnu11 -ffreestanding -O2 -Wall -Wextra -fno-pic -fno-pie -fno-stack-protector -m32
LDFLAGS := -T linker.ld -ffreestanding -O2 -nostdlib -m32
LIBS := -lgcc

.PHONY: all iso run clean

all: $(ISO)

iso: $(ISO)

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/boot.o: boot.asm | $(BUILD)
	$(AS) -f elf32 $< -o $@

$(BUILD)/kernel.o: kernel.c | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(KERNEL): $(BUILD)/boot.o $(BUILD)/kernel.o linker.ld
	$(CC) $(LDFLAGS) -o $@ $(BUILD)/boot.o $(BUILD)/kernel.o $(LIBS)
	grub-file --is-x86-multiboot $@

$(ISO): $(KERNEL) grub.cfg
	mkdir -p $(ISO_DIR)/boot/grub
	cp $(KERNEL) $(ISO_DIR)/boot/mmuko-kernel.bin
	cp grub.cfg $(ISO_DIR)/boot/grub/grub.cfg
	grub-mkrescue -o $(ISO) $(ISO_DIR)

run: $(ISO)
	$(QEMU) -cdrom $(ISO) -serial stdio -no-reboot -no-shutdown

clean:
	rm -rf $(BUILD)
