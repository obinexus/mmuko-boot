CROSS ?= i686-elf-
CC := $(CROSS)gcc
AS := nasm
QEMU ?= qemu-system-i386

BUILD := build
ISO_DIR := $(BUILD)/iso
KERNEL := $(BUILD)/mmuko-kernel.bin
ISO := $(BUILD)/mmuko.iso
DIRECT_IMAGE := $(BUILD)/mmuko-direct.img

CFLAGS := -std=gnu11 -ffreestanding -O2 -Wall -Wextra -fno-pic -fno-pie -fno-stack-protector -m32
LDFLAGS := -T linker.ld -ffreestanding -O2 -nostdlib -m32
LIBS := -lgcc

ifeq ($(OS),Windows_NT)
CHECK_CMD = where
CHECK_NULL = >NUL 2>NUL
PS_DIRECT = powershell -ExecutionPolicy Bypass -File .\build-direct.ps1
CLEAN_CMD = powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path '$(BUILD)') { try { Remove-Item -Recurse -Force '$(BUILD)' -ErrorAction Stop } catch { Write-Error 'Unable to remove build/. If QEMU is still running, stop it first with Ctrl+C and retry make clean.'; exit 1 } }"
else
CHECK_CMD = command -v
CHECK_NULL = >/dev/null 2>&1
PS_DIRECT = powershell.exe -ExecutionPolicy Bypass -File .\\build-direct.ps1
CLEAN_CMD = rm -rf $(BUILD)
endif

.PHONY: all iso run direct run-direct help check-grub-tools clean

all: $(ISO)

iso: $(ISO)

help:
	@echo "Targets:"
	@echo "  make help        - Show available targets"
	@echo "  make             - Build the GRUB ISO (requires i686-elf-gcc + GRUB tools)"
	@echo "  make iso         - Build the GRUB ISO"
	@echo "  make run         - Boot the GRUB ISO in QEMU"
	@echo "  make direct      - Build the Windows-friendly direct boot image"
	@echo "  make run-direct  - Build and boot the direct image in QEMU"
	@echo "  make clean       - Remove build artifacts"
	@echo ""
	@echo "Toolchain notes:"
	@echo "  GRUB path expects: $(CC), $(AS), grub-file, grub-mkrescue, $(QEMU)"
	@echo "  Direct path expects: PowerShell plus as, gcc, ld, objcopy, $(QEMU)"

check-grub-tools:
	@$(CHECK_CMD) $(CC) $(CHECK_NULL) || (echo ERROR: Missing $(CC). Install an i686 cross-compiler or run make direct. && exit 1)
	@$(CHECK_CMD) $(AS) $(CHECK_NULL) || (echo ERROR: Missing $(AS). && exit 1)
	@$(CHECK_CMD) grub-file $(CHECK_NULL) || (echo ERROR: Missing grub-file. Install GRUB tools or run make direct. && exit 1)
	@$(CHECK_CMD) grub-mkrescue $(CHECK_NULL) || (echo ERROR: Missing grub-mkrescue. Install GRUB tools or run make direct. && exit 1)

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/boot.o: boot.asm | $(BUILD)
	$(AS) -f elf32 $< -o $@

$(BUILD)/kernel.o: kernel.c | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(KERNEL): check-grub-tools $(BUILD)/boot.o $(BUILD)/kernel.o linker.ld
	$(CC) $(LDFLAGS) -o $@ $(BUILD)/boot.o $(BUILD)/kernel.o $(LIBS)
	grub-file --is-x86-multiboot $@

$(ISO): $(KERNEL) grub.cfg
	mkdir -p $(ISO_DIR)/boot/grub
	cp $(KERNEL) $(ISO_DIR)/boot/mmuko-kernel.bin
	cp grub.cfg $(ISO_DIR)/boot/grub/grub.cfg
	grub-mkrescue -o $(ISO) $(ISO_DIR)

run: $(ISO)
	$(QEMU) -cdrom $(ISO) -serial stdio -no-reboot -no-shutdown

$(DIRECT_IMAGE): build-direct.ps1 boot16.s kernel-entry.s kernel.c linker-flat.ld
	$(PS_DIRECT)

direct: $(DIRECT_IMAGE)

run-direct: $(DIRECT_IMAGE)
	$(QEMU) -drive format=raw,file=$(DIRECT_IMAGE),if=ide,index=0 -display none -serial stdio -no-reboot

clean:
	$(CLEAN_CMD)
